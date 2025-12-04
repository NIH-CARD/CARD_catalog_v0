#!/usr/bin/env python3
"""
CARD Catalog - GitHub Repository Scraper
Searches GitHub for code repositories related to neurodegenerative disease studies
Includes AI-powered analysis for biomedical relevance, summaries, data types, and tooling
"""
import pandas as pd
import requests
import time
import os
from typing import List, Dict, Optional
import json
import re
import sys
from anthropic import Anthropic
from datetime import datetime
import base64
import argparse

class SearchRateLimiter:
    """Rate limiter for GitHub search API - enforces 25 searches per minute"""
    def __init__(self, max_requests_per_minute: int = 25):
        self.max_requests = max_requests_per_minute
        self.request_times = []

    def wait_if_needed(self):
        """Wait if we've exceeded the rate limit"""
        now = time.time()
        # Remove requests older than 60 seconds
        self.request_times = [t for t in self.request_times if now - t < 60]

        if len(self.request_times) >= self.max_requests:
            # Calculate how long to wait
            oldest_request = self.request_times[0]
            wait_time = 60 - (now - oldest_request) + 1  # +1 second buffer
            if wait_time > 0:
                print(f"Search rate limit: {len(self.request_times)}/25 in last minute. Waiting {int(wait_time)} seconds...", file=sys.stderr)
                time.sleep(wait_time)
                # Clean up old requests again after waiting
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 60]

        # Record this request
        self.request_times.append(time.time())

class FAIRComplianceLogger:
    """Logger for tracking FAIR compliance issues in GitHub repositories"""
    def __init__(self, output_file: str = None):
        self.issues = []
        self.stats = {
            'total_repos': 0,
            'no_readme': 0,
            'insufficient_content': 0,
            'no_dependencies': 0,
            'no_version_info': 0,
            'no_environment_info': 0,
            'no_container': 0,
            'has_container': 0,
            'has_version_info': 0,
            'has_dependencies': 0
        }
        self.output_file = output_file or f"fair_compliance_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tsv"

    def log_issue(self, repo_url: str, study_name: str, issue_type: str, details: str):
        """Log a FAIR compliance issue"""
        self.issues.append({
            'Repository': repo_url,
            'Study': study_name,
            'Issue Type': issue_type,
            'Details': details,
            'Timestamp': datetime.now().isoformat()
        })

    def increment_stat(self, stat_name: str):
        """Increment a statistic counter"""
        if stat_name in self.stats:
            self.stats[stat_name] += 1

    def save_log(self):
        """Save the FAIR compliance log to a file"""
        if self.issues:
            df = pd.DataFrame(self.issues)
            df.to_csv(self.output_file, sep='\t', index=False)
            print(f"\nFAIR compliance log saved to {self.output_file}", file=sys.stderr)

    def print_summary(self):
        """Print a summary of FAIR compliance statistics"""
        print(f"\n{'='*60}", file=sys.stderr)
        print("FAIR COMPLIANCE SUMMARY", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"Total repositories analyzed: {self.stats['total_repos']}", file=sys.stderr)
        print(f"\nIssues Found:", file=sys.stderr)
        print(f"  No README: {self.stats['no_readme']} ({self.stats['no_readme']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  Insufficient content: {self.stats['insufficient_content']} ({self.stats['insufficient_content']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  No dependency info: {self.stats['no_dependencies']} ({self.stats['no_dependencies']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  No version info: {self.stats['no_version_info']} ({self.stats['no_version_info']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  No environment info: {self.stats['no_environment_info']} ({self.stats['no_environment_info']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  No container: {self.stats['no_container']} ({self.stats['no_container']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"\nFAIR Best Practices:", file=sys.stderr)
        print(f"  Has container (Docker/etc): {self.stats['has_container']} ({self.stats['has_container']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  Has version info: {self.stats['has_version_info']} ({self.stats['has_version_info']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"  Has dependencies: {self.stats['has_dependencies']} ({self.stats['has_dependencies']/max(self.stats['total_repos'],1)*100:.1f}%)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

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
                        print(f"Rate limit exceeded. Waiting {int(wait_time)} seconds...", file=sys.stderr)
                        time.sleep(wait_time)
                        continue

                delay = base_delay * (2 ** attempt)
                print(f"GitHub API error 403 (attempt {attempt + 1}/{max_retries}). Waiting {delay} seconds...", file=sys.stderr)
                time.sleep(delay)
            elif response.status_code == 404:
                # Not found is a valid response, return it
                return response
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {delay} seconds...", file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"Request failed after {max_retries} attempts: {str(e)}", file=sys.stderr)
                return None
    return None

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

        # Create the analysis prompt
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
        print(f"Error in AI analysis: {str(e)}", file=sys.stderr)
        return {
            "biomedical_relevance": f"ERROR - {str(e)}",
            "summary": "",
            "data_types": "",
            "tools": ""
        }

def check_fair_compliance(owner: str, repo_name: str, headers: Dict, fair_logger: FAIRComplianceLogger, repo_url: str, study_name: str) -> Dict:
    """Check repository for FAIR compliance indicators"""
    compliance_info = {
        'has_readme': False,
        'has_dependencies': False,
        'has_version_info': False,
        'has_container': False,
        'has_environment': False,
        'content_length': 0
    }

    # Check for README
    readme_url = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
    readme_response = github_request_with_retry(readme_url, headers)
    if readme_response and readme_response.status_code == 200:
        compliance_info['has_readme'] = True
        fair_logger.increment_stat('has_dependencies')  # Will be corrected below if false

    # Check for dependency files
    dependency_files = ['requirements.txt', 'package.json', 'setup.py', 'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle']
    for dep_file in dependency_files:
        file_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{dep_file}"
        response = github_request_with_retry(file_url, headers)
        if response and response.status_code == 200:
            compliance_info['has_dependencies'] = True
            fair_logger.increment_stat('has_dependencies')
            break

    # Check for version/environment files
    version_files = ['.python-version', '.nvmrc', 'runtime.txt', '.tool-versions']
    for ver_file in version_files:
        file_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{ver_file}"
        response = github_request_with_retry(file_url, headers)
        if response and response.status_code == 200:
            compliance_info['has_version_info'] = True
            fair_logger.increment_stat('has_version_info')
            break

    # Check for container files
    container_files = ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.dockerignore', 'Containerfile']
    for cont_file in container_files:
        file_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{cont_file}"
        response = github_request_with_retry(file_url, headers)
        if response and response.status_code == 200:
            compliance_info['has_container'] = True
            fair_logger.increment_stat('has_container')
            break

    # Check for environment specification
    env_files = ['environment.yml', 'environment.yaml', 'conda.yml', 'Pipfile', 'poetry.lock']
    for env_file in env_files:
        file_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{env_file}"
        response = github_request_with_retry(file_url, headers)
        if response and response.status_code == 200:
            compliance_info['has_environment'] = True
            break

    # Log FAIR compliance issues
    if not compliance_info['has_readme']:
        fair_logger.increment_stat('no_readme')
        fair_logger.log_issue(repo_url, study_name, 'No README', 'Repository lacks a README file, reducing accessibility and understandability')

    if not compliance_info['has_dependencies']:
        fair_logger.increment_stat('no_dependencies')
        fair_logger.log_issue(repo_url, study_name, 'No Dependencies', 'No dependency file found (requirements.txt, package.json, etc.), reducing reproducibility')

    if not compliance_info['has_version_info']:
        fair_logger.increment_stat('no_version_info')
        fair_logger.log_issue(repo_url, study_name, 'No Version Info', 'No version specification file found, may cause compatibility issues')

    if not compliance_info['has_container']:
        fair_logger.increment_stat('no_container')
        fair_logger.log_issue(repo_url, study_name, 'No Container', 'No Docker or container file found, limiting reproducibility across environments')

    if not compliance_info['has_environment']:
        fair_logger.increment_stat('no_environment_info')
        fair_logger.log_issue(repo_url, study_name, 'No Environment Spec', 'No environment specification file (conda, pipenv, etc.) found')

    return compliance_info

def get_repo_content(owner: str, repo_name: str, headers: Dict, fair_logger: FAIRComplianceLogger = None, repo_url: str = "", study_name: str = "") -> str:
    """Get repository content (README and optionally source files)"""
    content_parts = []

    # Try to get README
    readme_url = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
    readme_response = github_request_with_retry(readme_url, headers)

    if readme_response and readme_response.status_code == 200:
        try:
            readme_data = readme_response.json()
            if readme_data and 'content' in readme_data:
                # Decode base64 content
                readme_content = base64.b64decode(readme_data['content']).decode('utf-8', errors='ignore')
                content_parts.append(f"README:\n{readme_content}")
        except Exception as e:
            print(f"  Error parsing README: {str(e)}", file=sys.stderr)

    # If README is too short or missing, try to get package.json, setup.py, or requirements.txt
    if len(content_parts) == 0 or len(content_parts[0]) < 200:
        for filename in ['package.json', 'setup.py', 'requirements.txt', 'Cargo.toml', 'go.mod']:
            file_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{filename}"
            file_response = github_request_with_retry(file_url, headers)

            if file_response and file_response.status_code == 200:
                try:
                    file_data = file_response.json()
                    if file_data and 'content' in file_data:
                        file_content = base64.b64decode(file_data['content']).decode('utf-8', errors='ignore')
                        content_parts.append(f"{filename}:\n{file_content[:1000]}")
                        break  # Only get one additional file
                except Exception as e:
                    continue

    return "\n\n".join(content_parts)

def search_github(study_name: str, abbreviation: str, diseases: str, github_token: str, fair_logger: FAIRComplianceLogger, rate_limiter: SearchRateLimiter) -> List[Dict]:
    """Search GitHub for repositories related to the study"""
    disease_keywords = ["alzheimer", "parkinson", "dementia", "brain"]

    all_results = []
    seen_repos = set()

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # GitHub search has issues with long quoted phrases causing 422 errors
    # Solution: Use abbreviations only (no quotes) for more reliable searches

    if not abbreviation or not abbreviation.strip():
        print(f"  No abbreviation available - skipping GitHub search", file=sys.stderr)
        return all_results

    # Search combinations: abbreviation + each disease keyword (no quotes)
    for disease_term in disease_keywords:
        query = f'{abbreviation} {disease_term}'  # No quotes = more flexible
        print(f"  Searching: {query}", file=sys.stderr)
        results = search_github_with_query(query, study_name, abbreviation, diseases, headers, seen_repos, fair_logger, rate_limiter)
        all_results.extend(results)

    return all_results

def search_github_with_query(query: str, study_name: str, abbreviation: str, diseases: str, headers: Dict, seen_repos: set, fair_logger: FAIRComplianceLogger, rate_limiter: SearchRateLimiter) -> List[Dict]:
    """Perform a single GitHub search with a specific query"""
    # Enforce rate limit before making search request
    rate_limiter.wait_if_needed()

    url = 'https://api.github.com/search/repositories'
    params = {
        'q': query,
        'sort': 'stars',
        'order': 'desc',
        'per_page': 30  # Match beta version that successfully completed
    }

    response = github_request_with_retry(url, headers, params)
    if not response or response.status_code != 200:
        return []

    try:
        data = response.json()
        items = data.get('items', [])

        if not items:
            print(f"  No repositories found", file=sys.stderr)
            return []

        print(f"  Found {len(items)} repositories", file=sys.stderr)

        results = []
        for idx, repo in enumerate(items):
            try:
                repo_url = repo['html_url']

                # Skip if already seen
                if repo_url in seen_repos:
                    continue

                seen_repos.add(repo_url)
                fair_logger.increment_stat('total_repos')

                owner = repo['owner']['login']
                repo_name = repo['name']
                languages = repo.get('language', '')

                # Check FAIR compliance
                compliance_info = check_fair_compliance(owner, repo_name, headers, fair_logger, repo_url, study_name)

                # Get contributors
                contributors = []
                contributors_url = repo['contributors_url']
                contributors_response = github_request_with_retry(contributors_url, headers)

                if contributors_response and contributors_response.status_code == 200:
                    try:
                        contributors_data = contributors_response.json()
                        if contributors_data:
                            contributors = [c['login'] for c in contributors_data[:10] if isinstance(c, dict) and 'login' in c]
                    except Exception as e:
                        print(f"  Error parsing contributors: {str(e)}", file=sys.stderr)

                # Get repository content
                print(f"  Analyzing: {repo_url}", file=sys.stderr)
                repo_content = get_repo_content(owner, repo_name, headers, fair_logger, repo_url, study_name)

                # Get AI analysis
                ai_analysis = get_ai_analysis(repo_content, repo_name)

                # Skip if no content could be analyzed
                if not repo_content or len(repo_content) < 50:
                    print(f"  Skipping {repo_url} - insufficient content", file=sys.stderr)
                    fair_logger.increment_stat('insufficient_content')
                    fair_logger.log_issue(repo_url, study_name, 'Insufficient Content',
                                         f'Repository content too short (<50 chars), may be incomplete or non-functional')
                    continue

                results.append({
                    "Study Name": study_name,
                    "Abbreviation": abbreviation,
                    "Diseases Included": diseases,
                    "Repository Link": repo_url,
                    "Owner": owner,
                    "Contributors": "; ".join(contributors),
                    "Languages": languages,
                    "Biomedical Relevance": ai_analysis["biomedical_relevance"],
                    "Code Summary": ai_analysis["summary"],
                    "Data Types": ai_analysis["data_types"],
                    "Tooling": ai_analysis["tools"]
                })

            except Exception as e:
                print(f"  Error processing repository: {str(e)}", file=sys.stderr)
                continue

        print(f"  Successfully processed {len(results)} repositories", file=sys.stderr)
        return results

    except Exception as e:
        print(f"  Error searching GitHub: {str(e)}", file=sys.stderr)
        return []

def main():
    parser = argparse.ArgumentParser(description='Scrape GitHub for code repositories related to neurodegenerative disease studies')
    parser.add_argument('--input', '-i', default='../tables/dataset-inventory-June_20_2025.tab',
                       help='Input TSV file with study inventory (default: ../tables/dataset-inventory-June_20_2025.tab)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output TSV file (default: gits_to_reannotate_completed_{timestamp}.tsv)')
    parser.add_argument('--start', '-s', type=int, default=0,
                       help='Start index (0-based) for processing studies (default: 0)')
    parser.add_argument('--end', '-e', type=int, default=None,
                       help='End index (exclusive) for processing studies (default: all)')
    parser.add_argument('--github-token', '-g', default=None,
                       help='GitHub API token (default: from GITHUB_TOKEN env var)')
    parser.add_argument('--anthropic-key', '-a', default=None,
                       help='Anthropic API key (default: from ANTHROPIC_API_KEY env var)')

    args = parser.parse_args()

    # Check for required environment variables
    github_token = args.github_token or os.getenv('GITHUB_TOKEN')
    anthropic_key = args.anthropic_key or os.getenv('ANTHROPIC_API_KEY')

    if not github_token:
        print("Error: GitHub token required. Set GITHUB_TOKEN env var or use --github-token", file=sys.stderr)
        sys.exit(1)

    if not anthropic_key:
        print("Error: Anthropic API key required. Set ANTHROPIC_API_KEY env var or use --anthropic-key", file=sys.stderr)
        sys.exit(1)

    # Set environment variable for get_anthropic_client()
    if args.anthropic_key:
        os.environ['ANTHROPIC_API_KEY'] = args.anthropic_key

    # Initialize FAIR compliance logger
    fair_logger = FAIRComplianceLogger()

    # Initialize rate limiter for search API (25 requests per minute)
    rate_limiter = SearchRateLimiter(max_requests_per_minute=25)

    # Read the dataset inventory
    try:
        studies_df = pd.read_csv(args.input, sep="\t")
        print(f"Loaded {len(studies_df)} studies from {args.input}", file=sys.stderr)
    except Exception as e:
        print(f"Error reading dataset inventory: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Apply batch slicing
    end_idx = args.end if args.end is not None else len(studies_df)
    studies_df = studies_df.iloc[args.start:end_idx]
    print(f"Processing studies {args.start} to {end_idx-1} ({len(studies_df)} studies in this batch)", file=sys.stderr)

    # Initialize results list
    all_results = []

    # Process each study
    for idx, row in studies_df.iterrows():
        study_name = row.get("Study Name", "")
        abbreviation = row.get("Abbreviation", "")
        diseases = row.get("Diseases Included", "")

        print(f"\n[{idx+1}/{len(studies_df)}] Searching GitHub for repositories related to {study_name} ({abbreviation})...", file=sys.stderr)
        results = search_github(study_name, abbreviation, diseases, github_token, fair_logger, rate_limiter)
        all_results.extend(results)

    # Remove duplicates
    print("\nRemoving duplicate repositories...", file=sys.stderr)
    seen_combinations = set()
    deduplicated_results = []

    for result in all_results:
        repo_link = result.get("Repository Link", "")
        study_name = result.get("Study Name", "")
        combination_key = f"{repo_link}_{study_name}"

        if combination_key not in seen_combinations:
            seen_combinations.add(combination_key)
            deduplicated_results.append(result)

    # Create and save results dataframe
    if deduplicated_results:
        # Reorder columns to match previous format
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

        results_df = pd.DataFrame(deduplicated_results)

        # Ensure all columns exist
        for col in columns_order:
            if col not in results_df.columns:
                results_df[col] = ""

        # Reorder columns
        results_df = results_df[columns_order]

        # Generate output filename
        if args.output:
            output_filename = args.output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"../tables/gits_to_reannotate_completed_{timestamp}.tsv"

        results_df.to_csv(output_filename, sep="\t", index=False)

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"SUCCESS: Results saved to {output_filename}", file=sys.stderr)
        print(f"Total repositories found: {len(deduplicated_results)}", file=sys.stderr)
        print(f"Duplicates removed: {len(all_results) - len(deduplicated_results)}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        # Save and print FAIR compliance log
        fair_logger.save_log()
        fair_logger.print_summary()
    else:
        print("\nNo results found", file=sys.stderr)
        fair_logger.save_log()
        fair_logger.print_summary()
        sys.exit(1)

if __name__ == "__main__":
    main()
