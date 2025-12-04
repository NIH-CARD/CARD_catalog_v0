#!/usr/bin/env python3
"""
CARD Catalog - Reprocess Insufficient Content Repositories
Reprocesses repositories that were previously skipped due to insufficient content
by performing deep directory searches for README, notebooks, and code files
"""
import pandas as pd
import requests
import time
import os
from typing import List, Dict, Optional, Set, Tuple
import json
import re
import sys
from anthropic import Anthropic
from datetime import datetime
import base64
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


def clean_text(text: str) -> str:
    """Remove newlines and extra whitespace from text"""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', text.strip())


def get_anthropic_client():
    """Initialize Anthropic client"""
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key:
            client = Anthropic(api_key=api_key)
            return client
        else:
            print("ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Failed to initialize Anthropic client: {e}", file=sys.stderr)
        return None


def github_request_with_retry(url: str, headers: Dict, params: Dict = None, max_retries: int = 3, base_delay: int = 60) -> Optional[requests.Response]:
    """Make a GitHub API request with exponential backoff retry logic"""
    for attempt in range(max_retries):
        try:
            time.sleep(5)  # Rate limiting: minimum 5 seconds between all GitHub API requests
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                # Check if it's a rate limit issue
                if 'X-RateLimit-Remaining' in response.headers:
                    remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
                    if remaining == 0:
                        reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                        wait_time = max(reset_time - time.time(), base_delay)
                        print(f"  Rate limit exceeded. Waiting {int(wait_time)} seconds...", file=sys.stderr)
                        time.sleep(wait_time)
                        continue

                delay = base_delay * (2 ** attempt)
                print(f"  GitHub API error 403 (attempt {attempt + 1}/{max_retries}). Waiting {delay} seconds...", file=sys.stderr)
                time.sleep(delay)
            elif response.status_code == 404:
                # Not found is a valid response, return it
                return response
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"  Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {delay} seconds...", file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"  Request failed after {max_retries} attempts: {str(e)}", file=sys.stderr)
                return None
    return None


def parse_batch_logs(log_dir: str) -> Dict[str, Dict[str, str]]:
    """
    Parse batch log files to extract repos that were skipped with "insufficient content"
    and map them to their study info.

    Returns: dict mapping repo_url -> {study_name, abbreviation}
    """
    log_files = [
        'github_batch1of4.log',
        'github_batch2of4.log',
        'github_batch3of4.log',
        'github_batch4of4.log'
    ]

    repo_mapping = {}
    current_study_name = None
    current_abbreviation = None

    print("\nParsing batch log files:", file=sys.stderr)
    for log_file in log_files:
        log_path = os.path.join(log_dir, log_file)
        if not os.path.exists(log_path):
            print(f"  Warning: Log file not found: {log_path}", file=sys.stderr)
            continue

        print(f"  Reading {log_file}...", file=sys.stderr)
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Match study search lines
                study_match = re.search(r'Searching GitHub for repositories related to (.+?) \((.+?)\)\.\.\.', line)
                if study_match:
                    current_study_name = study_match.group(1)
                    current_abbreviation = study_match.group(2)
                    continue

                # Match skipped repo lines
                skip_match = re.search(r'Skipping (https://github\.com/[^\s]+) - insufficient content', line)
                if skip_match and current_study_name and current_abbreviation:
                    repo_url = skip_match.group(1)
                    repo_mapping[repo_url] = {
                        'study_name': current_study_name,
                        'abbreviation': current_abbreviation
                    }

    print(f"\nFound {len(repo_mapping)} repositories with insufficient content", file=sys.stderr)
    return repo_mapping


def load_disease_information(dataset_file: str) -> Dict[str, str]:
    """
    Load disease information from dataset inventory file.

    Returns: dict mapping abbreviation -> diseases_included
    """
    try:
        print(f"\nLoading disease information from {dataset_file}...", file=sys.stderr)
        df = pd.read_csv(dataset_file, sep='\t')
        disease_map = {}

        for _, row in df.iterrows():
            abbr = row.get('Abbreviation', '')
            diseases = row.get('Diseases Included', '')
            if abbr and diseases:
                disease_map[abbr] = diseases

        print(f"  Loaded disease information for {len(disease_map)} studies", file=sys.stderr)
        return disease_map
    except Exception as e:
        print(f"  Error loading disease information: {e}", file=sys.stderr)
        return {}


def search_directory_tree(owner: str, repo_name: str, headers: Dict, path: str = "", level: int = 0, max_level: int = 2) -> Dict:
    """
    Search directory tree up to max_level depth for README, notebooks, and code files.

    Returns: dict with content info and statistics
    """
    result = {
        'readme_content': '',
        'notebook_content': '',
        'code_files': [],
        'has_readme': False,
        'notebook_count': 0,
        'code_file_count': 0,
        'directories_searched': []
    }

    if level > max_level:
        return result

    # Get contents of current directory
    contents_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{path}"
    response = github_request_with_retry(contents_url, headers)

    if not response or response.status_code != 200:
        return result

    try:
        contents = response.json()
        if not isinstance(contents, list):
            return result

        result['directories_searched'].append(path if path else '/')

        # Process files and directories
        for item in contents:
            item_name = item.get('name', '').lower()
            item_type = item.get('type', '')
            item_path = item.get('path', '')

            # Check for README
            if item_type == 'file' and item_name.startswith('readme'):
                if not result['has_readme']:
                    file_response = github_request_with_retry(item['url'], headers)
                    if file_response and file_response.status_code == 200:
                        try:
                            file_data = file_response.json()
                            if file_data and 'content' in file_data:
                                content = base64.b64decode(file_data['content']).decode('utf-8', errors='ignore')
                                result['readme_content'] = content
                                result['has_readme'] = True
                                print(f"      Found README at: {item_path}", file=sys.stderr)
                        except Exception as e:
                            print(f"      Error reading README: {e}", file=sys.stderr)

            # Check for notebooks
            elif item_type == 'file' and item_name.endswith('.ipynb'):
                result['notebook_count'] += 1
                file_response = github_request_with_retry(item['url'], headers)
                if file_response and file_response.status_code == 200:
                    try:
                        file_data = file_response.json()
                        if file_data and 'content' in file_data:
                            content = base64.b64decode(file_data['content']).decode('utf-8', errors='ignore')
                            # Extract first 1000 chars of notebook
                            result['notebook_content'] += f"\n\nNotebook: {item_path}\n{content[:1000]}"
                            print(f"      Found notebook: {item_path}", file=sys.stderr)
                    except Exception as e:
                        print(f"      Error reading notebook: {e}", file=sys.stderr)

            # Check for code files
            elif item_type == 'file':
                code_extensions = ['.py', '.r', '.m', '.jl', '.java', '.cpp', '.c', '.js', '.go', '.rs']
                if any(item_name.endswith(ext) for ext in code_extensions):
                    result['code_file_count'] += 1
                    result['code_files'].append(item_path)
                    if result['code_file_count'] <= 3:  # Only read first 3 code files
                        file_response = github_request_with_retry(item['url'], headers)
                        if file_response and file_response.status_code == 200:
                            try:
                                file_data = file_response.json()
                                if file_data and 'content' in file_data:
                                    content = base64.b64decode(file_data['content']).decode('utf-8', errors='ignore')
                                    # Add to readme content for analysis
                                    result['readme_content'] += f"\n\nCode file: {item_path}\n{content[:500]}"
                                    print(f"      Found code file: {item_path}", file=sys.stderr)
                            except Exception as e:
                                print(f"      Error reading code file: {e}", file=sys.stderr)

            # Recurse into subdirectories
            elif item_type == 'dir' and level < max_level:
                # Skip common directories that won't have relevant content
                skip_dirs = ['.git', 'node_modules', '__pycache__', '.vscode', '.idea', 'dist', 'build']
                if item_name not in skip_dirs:
                    subdir_result = search_directory_tree(owner, repo_name, headers, item_path, level + 1, max_level)
                    # Merge results
                    if not result['has_readme'] and subdir_result['has_readme']:
                        result['readme_content'] = subdir_result['readme_content']
                        result['has_readme'] = True
                    result['notebook_content'] += subdir_result['notebook_content']
                    result['notebook_count'] += subdir_result['notebook_count']
                    result['code_file_count'] += subdir_result['code_file_count']
                    result['code_files'].extend(subdir_result['code_files'])
                    result['directories_searched'].extend(subdir_result['directories_searched'])

    except Exception as e:
        print(f"      Error searching directory {path}: {e}", file=sys.stderr)

    return result


def get_ai_analysis(content: str, repo_name: str) -> Dict:
    """Use Claude to analyze repository content and extract biomedical relevance, summary, data types, and tools"""
    if not content or not content.strip():
        return {
            "biomedical_relevance": "UNKNOWN - No content available for analysis",
            "summary": "",
            "data_types": "",
            "tools": ""
        }

    try:
        client = get_anthropic_client()
        if not client:
            return {
                "biomedical_relevance": "UNKNOWN - AI client not available",
                "summary": "",
                "data_types": "",
                "tools": ""
            }

        # Create the analysis prompt (identical to main scraper)
        prompt = f"""Analyze this GitHub repository and provide:

1. BIOMEDICAL RELEVANCE: Answer YES or NO with a brief explanation. The repository is biomedically relevant if it relates to:
   - Neurodegenerative diseases (Alzheimer's, Parkinson's, dementia, ALS, etc.)
   - Brain imaging, neuroimaging, or brain analysis
   - Medical/clinical data analysis for brain disorders
   - Bioinformatics related to neuroscience
   - Healthcare applications for neurological conditions
   Answer NO if it's a general software project, web app, game, or unrelated to biomedical research.

2. CODE SUMMARY: Provide a concise 2-3 sentence summary of what the code does and its purpose.

3. DATA TYPES: List the data types and modalities mentioned (e.g., MRI, clinical data, genomics, etc.). If none are clearly specified, state "Not specified in the available repository information."

4. TOOLING: List the packages, tools, frameworks, and technologies used.

Repository: {repo_name}
Content (first 8000 chars):
{content[:8000]}

Format your response EXACTLY as follows (use these exact section headers):

BIOMEDICAL RELEVANCE:
[Your YES/NO answer with explanation]

CODE SUMMARY:
[Your 2-3 sentence summary]

DATA TYPES:
[Your data types list or "Not specified"]

TOOLING:
[Your tools list]"""

        # Make the API call
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            temperature=0.3,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Extract the response content
        content_text = response.content[0].text.strip()

        # Parse the response into sections
        sections = {
            "biomedical_relevance": "",
            "summary": "",
            "data_types": "",
            "tools": ""
        }

        # Split by section headers
        lines = content_text.split('\n')
        current_section = None
        section_content = []

        for line in lines:
            line_upper = line.strip().upper()
            if 'BIOMEDICAL RELEVANCE:' in line_upper:
                if current_section and section_content:
                    sections[current_section] = ' '.join(section_content).strip()
                current_section = "biomedical_relevance"
                section_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif 'CODE SUMMARY:' in line_upper:
                if current_section and section_content:
                    sections[current_section] = ' '.join(section_content).strip()
                current_section = "summary"
                section_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif 'DATA TYPES:' in line_upper:
                if current_section and section_content:
                    sections[current_section] = ' '.join(section_content).strip()
                current_section = "data_types"
                section_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif 'TOOLING:' in line_upper:
                if current_section and section_content:
                    sections[current_section] = ' '.join(section_content).strip()
                current_section = "tools"
                section_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif current_section and line.strip():
                section_content.append(line.strip())

        # Don't forget the last section
        if current_section and section_content:
            sections[current_section] = ' '.join(section_content).strip()

        # Clean up the sections
        for key in sections:
            sections[key] = clean_text(sections[key]) if sections[key] else ""

        return sections

    except Exception as e:
        print(f"      Error in AI analysis: {str(e)}", file=sys.stderr)
        return {
            "biomedical_relevance": f"ERROR - {str(e)}",
            "summary": "",
            "data_types": "",
            "tools": ""
        }


def get_repo_languages(owner: str, repo_name: str, headers: Dict) -> str:
    """Get repository languages from GitHub API"""
    languages_url = f"https://api.github.com/repos/{owner}/{repo_name}/languages"
    response = github_request_with_retry(languages_url, headers)

    if response and response.status_code == 200:
        try:
            languages = response.json()
            if languages:
                # Return the primary language (most bytes)
                return max(languages, key=languages.get)
        except Exception as e:
            print(f"      Error getting languages: {e}", file=sys.stderr)

    return ""


def get_repo_contributors(owner: str, repo_name: str, headers: Dict) -> List[str]:
    """Get repository contributors from GitHub API"""
    contributors_url = f"https://api.github.com/repos/{owner}/{repo_name}/contributors"
    response = github_request_with_retry(contributors_url, headers)

    if response and response.status_code == 200:
        try:
            contributors_data = response.json()
            if contributors_data:
                return [c['login'] for c in contributors_data[:10] if isinstance(c, dict) and 'login' in c]
        except Exception as e:
            print(f"      Error getting contributors: {e}", file=sys.stderr)

    return []


def reprocess_repo(repo_url: str, study_info: Dict, diseases_included: str, headers: Dict) -> Optional[Dict]:
    """
    Reprocess a repository with deep directory search.

    Returns: dict with repo info or None if truly empty
    """
    # Parse owner and repo name from URL
    match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
    if not match:
        print(f"    Could not parse repo URL: {repo_url}", file=sys.stderr)
        return None

    owner = match.group(1)
    repo_name = match.group(2)

    print(f"  Reprocessing: {repo_url}", file=sys.stderr)
    print(f"    Study: {study_info['study_name']} ({study_info['abbreviation']})", file=sys.stderr)
    print(f"    Searching repository tree (up to 2 levels deep)...", file=sys.stderr)

    # Perform deep directory search
    search_result = search_directory_tree(owner, repo_name, headers, "", 0, 2)

    # Check if truly empty
    if not search_result['has_readme'] and search_result['notebook_count'] == 0 and search_result['code_file_count'] == 0:
        print(f"    Result: SKIP - No content found (searched {len(search_result['directories_searched'])} directories)", file=sys.stderr)
        return None

    print(f"    Content found:", file=sys.stderr)
    print(f"      - README: {'Yes' if search_result['has_readme'] else 'No'}", file=sys.stderr)
    print(f"      - Notebooks: {search_result['notebook_count']}", file=sys.stderr)
    print(f"      - Code files: {search_result['code_file_count']}", file=sys.stderr)
    print(f"      - Directories searched: {len(search_result['directories_searched'])}", file=sys.stderr)

    # Combine all content for AI analysis
    combined_content = search_result['readme_content'] + search_result['notebook_content']

    if not combined_content or len(combined_content) < 50:
        print(f"    Result: SKIP - Combined content too short ({len(combined_content)} chars)", file=sys.stderr)
        return None

    # Get AI analysis
    print(f"    Running AI analysis (content length: {len(combined_content)} chars)...", file=sys.stderr)
    ai_analysis = get_ai_analysis(combined_content, repo_name)

    # Get contributors and languages
    print(f"    Fetching contributors and languages...", file=sys.stderr)
    contributors = get_repo_contributors(owner, repo_name, headers)
    languages = get_repo_languages(owner, repo_name, headers)

    print(f"    Result: SUCCESS - Repository processed", file=sys.stderr)

    return {
        "Study Name": study_info['study_name'],
        "Abbreviation": study_info['abbreviation'],
        "Diseases Included": diseases_included,
        "Repository Link": repo_url,
        "Owner": owner,
        "Contributors": "; ".join(contributors),
        "Languages": languages,
        "Biomedical Relevance": ai_analysis["biomedical_relevance"],
        "Code Summary": ai_analysis["summary"],
        "Data Types": ai_analysis["data_types"],
        "Tooling": ai_analysis["tools"]
    }


def main():
    print("="*80, file=sys.stderr)
    print("CARD CATALOG - REPROCESS INSUFFICIENT CONTENT REPOSITORIES", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
    print("="*80, file=sys.stderr)

    # Check for required environment variables
    github_token = os.getenv('GITHUB_TOKEN')
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')

    if not github_token:
        print("\nERROR: GITHUB_TOKEN not found in environment", file=sys.stderr)
        print("Please ensure the .env file exists in the scrapers directory", file=sys.stderr)
        sys.exit(1)

    if not anthropic_key:
        print("\nERROR: ANTHROPIC_API_KEY not found in environment", file=sys.stderr)
        print("Please ensure the .env file exists in the scrapers directory", file=sys.stderr)
        sys.exit(1)

    print("\nEnvironment variables loaded successfully", file=sys.stderr)

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Set up paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = script_dir
    dataset_file = os.path.join(script_dir, '..', 'tables', 'dataset-inventory-June_20_2025.tab')

    # Parse batch logs
    print("\n" + "="*80, file=sys.stderr)
    print("STEP 1: PARSING BATCH LOGS", file=sys.stderr)
    print("="*80, file=sys.stderr)
    repo_mapping = parse_batch_logs(log_dir)

    if not repo_mapping:
        print("\nNo repositories found to reprocess", file=sys.stderr)
        sys.exit(0)

    # Load disease information
    print("\n" + "="*80, file=sys.stderr)
    print("STEP 2: LOADING DISEASE INFORMATION", file=sys.stderr)
    print("="*80, file=sys.stderr)
    disease_map = load_disease_information(dataset_file)

    # Reprocess each repository
    print("\n" + "="*80, file=sys.stderr)
    print("STEP 3: REPROCESSING REPOSITORIES", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"Total repositories to reprocess: {len(repo_mapping)}", file=sys.stderr)
    print("="*80, file=sys.stderr)

    results = []
    processed_count = 0
    skipped_count = 0
    error_count = 0

    for idx, (repo_url, study_info) in enumerate(repo_mapping.items(), 1):
        print(f"\n[{idx}/{len(repo_mapping)}]", file=sys.stderr)

        # Get diseases included for this study
        abbreviation = study_info['abbreviation']
        diseases_included = disease_map.get(abbreviation, '')

        try:
            result = reprocess_repo(repo_url, study_info, diseases_included, headers)
            if result:
                results.append(result)
                processed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"    ERROR: {str(e)}", file=sys.stderr)
            error_count += 1
            continue

    # Save results
    print("\n" + "="*80, file=sys.stderr)
    print("STEP 4: SAVING RESULTS", file=sys.stderr)
    print("="*80, file=sys.stderr)

    if results:
        # Create DataFrame with exact column order
        columns_order = [
            "Study Name",
            "Abbreviation",
            "Diseases Included",
            "Repository Link",
            "Owner",
            "Contributors",
            "Languages",
            "Biomedical Relevance",
            "Code Summary",
            "Data Types",
            "Tooling"
        ]

        df = pd.DataFrame(results)

        # Ensure all columns exist
        for col in columns_order:
            if col not in df.columns:
                df[col] = ""

        # Reorder columns
        df = df[columns_order]

        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(script_dir, '..', 'tables', f'insufficient_reprocessed_{timestamp}.tsv')

        df.to_csv(output_file, sep='\t', index=False)

        print(f"\nOutput file: {output_file}", file=sys.stderr)
        print("\n" + "="*80, file=sys.stderr)
        print("FINAL STATISTICS", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"Total repositories in logs:          {len(repo_mapping)}", file=sys.stderr)
        print(f"Successfully processed:               {processed_count}", file=sys.stderr)
        print(f"Still insufficient content:           {skipped_count}", file=sys.stderr)
        print(f"Errors:                               {error_count}", file=sys.stderr)
        print(f"Processing rate:                      {processed_count}/{len(repo_mapping)} ({processed_count/len(repo_mapping)*100:.1f}%)", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
        print("="*80, file=sys.stderr)
    else:
        print("\nNo repositories had sufficient content after reprocessing", file=sys.stderr)
        print("\n" + "="*80, file=sys.stderr)
        print("FINAL STATISTICS", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"Total repositories checked:           {len(repo_mapping)}", file=sys.stderr)
        print(f"All repositories still empty:         {skipped_count}", file=sys.stderr)
        print(f"Errors:                               {error_count}", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
        print("="*80, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
