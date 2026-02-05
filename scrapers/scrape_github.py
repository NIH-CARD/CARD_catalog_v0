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
import logging
from logging_config import setup_logger, get_default_log_file
from dotenv import load_dotenv

try:
    load_dotenv()
except ImportError:
    pass

# Module-level logger - will be configured in main()
logger = logging.getLogger(__name__)

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
                logger.warning(f"Search rate limit: {len(self.request_times)}/25 in last minute. Waiting {int(wait_time)} seconds...")
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
            logger.info(f"FAIR compliance log saved to {self.output_file}")

    def print_summary(self):
        """Print a summary of FAIR compliance statistics"""
        logger.info(f"{'='*60}")
        logger.info("FAIR COMPLIANCE SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total repositories analyzed: {self.stats['total_repos']}")
        logger.info("Issues Found:")
        logger.info(f"  No README: {self.stats['no_readme']} ({self.stats['no_readme']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  Insufficient content: {self.stats['insufficient_content']} ({self.stats['insufficient_content']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  No dependency info: {self.stats['no_dependencies']} ({self.stats['no_dependencies']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  No version info: {self.stats['no_version_info']} ({self.stats['no_version_info']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  No environment info: {self.stats['no_environment_info']} ({self.stats['no_environment_info']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  No container: {self.stats['no_container']} ({self.stats['no_container']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info("FAIR Best Practices:")
        logger.info(f"  Has container (Docker/etc): {self.stats['has_container']} ({self.stats['has_container']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  Has version info: {self.stats['has_version_info']} ({self.stats['has_version_info']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"  Has dependencies: {self.stats['has_dependencies']} ({self.stats['has_dependencies']/max(self.stats['total_repos'],1)*100:.1f}%)")
        logger.info(f"{'='*60}")

def clean_text(text: str) -> str:
    """Remove newlines and extra whitespace from text"""
    logger.debug(f"Cleaning text: {len(text) if text else 0} chars")
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', text.strip())

def get_anthropic_client():
    """Initialize Anthropic client"""
    logger.debug("Initializing Anthropic client")
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key:
            client = Anthropic(api_key=api_key)
            return client
        else:
            logger.error("ANTHROPIC_API_KEY environment variable not set")
            return None
    except Exception as e:
        logger.error(f"Failed to initialize Anthropic client: {e}")
        return None

def github_request_with_retry(url: str, headers: Dict, params: Dict = None, max_retries: int = 3, base_delay: int = 60) -> Optional[requests.Response]:
    """Make a GitHub API request with exponential backoff retry logic"""
    logger.debug(f"GitHub API request: url={url}, params={params}, max_retries={max_retries}")
    for attempt in range(max_retries):
        try:
            time.sleep(3)  # Rate limiting: minimum 3 seconds between all GitHub API requests
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
                        logger.warning(f"Rate limit exceeded. Waiting {int(wait_time)} seconds...")
                        time.sleep(wait_time)
                        continue

                delay = base_delay * (2 ** attempt)
                logger.warning(f"GitHub API error 403 (attempt {attempt + 1}/{max_retries}). Waiting {delay} seconds...")
                time.sleep(delay)
            elif response.status_code == 404:
                # Not found is a valid response, return it
                return response
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"Request failed after {max_retries} attempts: {str(e)}")
                return None
    return None

def get_ai_analysis(content: str, repo_name: str) -> Dict:
    """Use Claude to analyze repository content and extract biomedical relevance, summary, data types, and tools"""
    logger.debug(f"Starting AI analysis for repository: {repo_name}, content length: {len(content) if content else 0} chars")
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
        logger.debug(f"Sending {len(prompt)} chars to Claude API for analysis")
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
        logger.debug(f"Received AI response, parsing sections...")

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

        logger.debug(f"AI analysis complete - Biomedical relevance: {sections['biomedical_relevance'][:50]}...")
        return sections

    except Exception as e:
        logger.error(f"Error in AI analysis: {str(e)}")
        return {
            "biomedical_relevance": f"ERROR - {str(e)}",
            "summary": "",
            "data_types": "",
            "tools": ""
        }

def get_repo_tree(owner: str, repo_name: str, default_branch: str, headers: Dict) -> Optional[set]:
    """Fetch repository file tree using Git Trees API (single request)"""
    logger.debug(f"Fetching git tree for {owner}/{repo_name} (branch: {default_branch})")
    
    try:
        # First, get the branch to find the tree SHA
        branch_url = f"https://api.github.com/repos/{owner}/{repo_name}/branches/{default_branch}"
        branch_response = github_request_with_retry(branch_url, headers)
        
        if not branch_response or branch_response.status_code != 200:
            logger.debug(f"Could not fetch branch {default_branch}, tree fetch failed")
            return None
        
        branch_data = branch_response.json()
        tree_sha = branch_data['commit']['commit']['tree']['sha']
        logger.debug(f"Tree SHA: {tree_sha}")
        
        # Fetch the recursive tree
        tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{tree_sha}"
        tree_response = github_request_with_retry(tree_url, headers, params={'recursive': '1'})
        
        if not tree_response or tree_response.status_code != 200:
            logger.warning("Tree API request failed")
            return None
        
        tree_data = tree_response.json()
        
        # Check if tree was truncated (>100k files)
        if tree_data.get('truncated', False):
            logger.warning(f"  Tree truncated for {owner}/{repo_name}, falling back to individual checks")
            return None
        
        # Extract all file paths into a set for O(1) lookup
        file_paths = {item['path'].lower() for item in tree_data.get('tree', []) if item['type'] == 'blob'}
        logger.debug(f"Fetched {len(file_paths)} file paths from tree")
        
        return file_paths
        
    except Exception as e:
        logger.warning(f"Error fetching git tree: {str(e)}")
        return None

def check_fair_compliance(owner: str, repo_name: str, default_branch: str, headers: Dict, fair_logger: FAIRComplianceLogger, repo_url: str, study_name: str) -> Dict:
    """Check repository for FAIR compliance indicators using Git Trees API"""
    logger.debug(f"Checking FAIR compliance for {owner}/{repo_name}")
    compliance_info = {
        'has_readme': False,
        'has_dependencies': False,
        'has_version_info': False,
        'has_container': False,
        'has_environment': False,
        'content_length': 0
    }

    # Try to get file tree (optimized approach - 2 API requests instead of ~22)
    file_paths = get_repo_tree(owner, repo_name, default_branch, headers)
    
    if file_paths:
        # Use tree-based checking (O(1) lookups)
        logger.debug("Using tree-based FAIR compliance checking")
        
        # Check for README (case-insensitive)
        readme_files = ['readme.md', 'readme.rst', 'readme.txt', 'readme']
        compliance_info['has_readme'] = any(f in file_paths for f in readme_files)
        
        # Check for dependency files
        dependency_files = ['requirements.txt', 'package.json', 'setup.py', 'cargo.toml', 'go.mod', 'pom.xml', 'build.gradle']
        compliance_info['has_dependencies'] = any(f in file_paths for f in dependency_files)
        if compliance_info['has_dependencies']:
            fair_logger.increment_stat('has_dependencies')
        
        # Check for version/environment files
        version_files = ['.python-version', '.nvmrc', 'runtime.txt', '.tool-versions']
        compliance_info['has_version_info'] = any(f in file_paths for f in version_files)
        if compliance_info['has_version_info']:
            fair_logger.increment_stat('has_version_info')
        
        # Check for container files
        container_files = ['dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.dockerignore', 'containerfile']
        compliance_info['has_container'] = any(f in file_paths for f in container_files)
        if compliance_info['has_container']:
            fair_logger.increment_stat('has_container')
        
        # Check for environment specification
        env_files = ['environment.yml', 'environment.yaml', 'conda.yml', 'pipfile', 'poetry.lock']
        compliance_info['has_environment'] = any(f in file_paths for f in env_files)
    
    else:
        # Fallback to individual file checks if tree not available
        logger.debug("Falling back to individual file checks")
        
        # Check for README
        readme_url = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
        readme_response = github_request_with_retry(readme_url, headers)
        if readme_response and readme_response.status_code == 200:
            compliance_info['has_readme'] = True
        
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
    logger.debug(f"Fetching content for repository: {owner}/{repo_name}")
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
                logger.debug(f"README fetched: {len(readme_content)} chars")
                content_parts.append(f"README:\n{readme_content}")
        except Exception as e:
            logger.warning(f"  Error parsing README: {str(e)}")

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
    logger.debug(f"Starting GitHub search for study: {study_name} ({abbreviation})")
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
        logger.info("  No abbreviation available - skipping GitHub search")
        return all_results

    # Search combinations: abbreviation + each disease keyword (no quotes)
    for disease_term in disease_keywords:
        query = f'{abbreviation} {disease_term}'  # No quotes = more flexible
        logger.debug(f"Constructed search query: {query}")
        logger.info(f"  Searching: {query}")
        results = search_github_with_query(query, study_name, abbreviation, diseases, headers, seen_repos, fair_logger, rate_limiter)
        all_results.extend(results)

    return all_results

def search_github_with_query(query: str, study_name: str, abbreviation: str, diseases: str, headers: Dict, seen_repos: set, fair_logger: FAIRComplianceLogger, rate_limiter: SearchRateLimiter) -> List[Dict]:
    """Perform a single GitHub search with a specific query"""
    logger.debug(f"Executing GitHub search: query='{query}', study={study_name}, abbreviation={abbreviation}")
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
            logger.info("  No repositories found")
            return []

        logger.info(f"  Found {len(items)} repositories")

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
                default_branch = repo.get('default_branch', 'main')

                # Check FAIR compliance
                compliance_info = check_fair_compliance(owner, repo_name, default_branch, headers, fair_logger, repo_url, study_name)

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
                        logger.warning(f"  Error parsing contributors: {str(e)}")

                # Get repository content
                logger.info(f"  Analyzing: {repo_url}")
                repo_content = get_repo_content(owner, repo_name, headers, fair_logger, repo_url, study_name)

                # Get AI analysis
                ai_analysis = get_ai_analysis(repo_content, repo_name)

                # Skip if no content could be analyzed
                if not repo_content or len(repo_content) < 50:
                    logger.info(f"  Skipping {repo_url} - insufficient content")
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
                logger.error(f"  Error processing repository: {str(e)}")
                continue

        logger.info(f"  Successfully processed {len(results)} repositories")
        return results

    except Exception as e:
        logger.error(f"  Error searching GitHub: {str(e)}")
        return []

def main():
    logger.debug("Starting main function")
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
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose (DEBUG) logging')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Suppress INFO logs, show only WARNING and ERROR')
    parser.add_argument('--log-file', '-l', default=None,
                       help='Log file path (default: github_scraper_{timestamp}.log)')

    args = parser.parse_args()

    # Setup logger
    log_level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    log_file = args.log_file or get_default_log_file('github_scraper')
    setup_logger(__name__, log_file, log_level)

    # Check for required environment variables
    github_token = args.github_token or os.getenv('GITHUB_TOKEN')
    anthropic_key = args.anthropic_key or os.getenv('ANTHROPIC_API_KEY')
    logger.debug(f"GitHub token present: {'YES' if github_token else 'NO'}")
    logger.debug(f"Anthropic key present: {'YES' if anthropic_key else 'NO'}")

    if not github_token:
        logger.error("Error: GitHub token required. Set GITHUB_TOKEN env var or use --github-token")
        sys.exit(1)

    if not anthropic_key:
        logger.error("Error: Anthropic API key required. Set ANTHROPIC_API_KEY env var or use --anthropic-key")
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
        logger.info(f"Loaded {len(studies_df)} studies from {args.input}")
    except Exception as e:
        logger.error(f"Error reading dataset inventory: {str(e)}")
        sys.exit(1)

    # Apply batch slicing
    end_idx = args.end if args.end is not None else len(studies_df)
    studies_df = studies_df.iloc[args.start:end_idx]
    logger.info(f"Processing studies {args.start} to {end_idx-1} ({len(studies_df)} studies in this batch)")
    logger.debug(f"Batch slice: start={args.start}, end={end_idx}, total_studies={len(studies_df)}")

    # Initialize results list
    all_results = []

    # Process each study
    for idx, row in studies_df.iterrows():
        study_name = row.get("Study Name", "")
        abbreviation = row.get("Abbreviation", "")
        diseases = row.get("Diseases Included", "")

        logger.info(f"[{idx+1}/{len(studies_df)}] Searching GitHub for repositories related to {study_name} ({abbreviation})...")
        results = search_github(study_name, abbreviation, diseases, github_token, fair_logger, rate_limiter)
        all_results.extend(results)

    # Remove duplicates
    logger.info("Removing duplicate repositories...")
    logger.debug(f"Total results before deduplication: {len(all_results)}")
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

        logger.info(f"{'='*60}")
        logger.info(f"SUCCESS: Results saved to {output_filename}")
        logger.info(f"Total repositories found: {len(deduplicated_results)}")
        logger.info(f"Duplicates removed: {len(all_results) - len(deduplicated_results)}")
        logger.info(f"{'='*60}")

        # Save and print FAIR compliance log
        fair_logger.save_log()
        fair_logger.print_summary()
    else:
        logger.info("No results found")
        fair_logger.save_log()
        fair_logger.print_summary()
        sys.exit(1)

if __name__ == "__main__":
    main()
