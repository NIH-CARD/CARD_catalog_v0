#!/usr/bin/env python3
"""
CARD Catalog - Batch AI Analysis for GitHub Repositories
Processes repositories collected by scrape_github.py --batch-call-ai using Anthropic's Batch API
Provides 50% cost savings compared to synchronous API calls
"""
import pandas as pd
import os
import sys
import json
import time
import argparse
import logging
from typing import Dict, List, Optional
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv
from logging_config import setup_logger, get_default_log_file
import re

try:
    load_dotenv()
except ImportError:
    pass

# Module-level logger
logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Remove newlines and extra whitespace from text"""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', text.strip())

def sanitize_custom_id(text: str, max_length: int = 64) -> str:
    """
    Sanitize text for use as Batch API custom_id
    custom_id must match pattern: ^[a-zA-Z0-9_-]{1,64}$
    """
    # Replace forward slashes with underscores
    text = text.replace('/', '_')
    # Replace any other invalid characters with underscores
    text = re.sub(r'[^a-zA-Z0-9_-]', '_', text)
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]
    return text

def create_analysis_prompt(repo_content: str, repo_name: str) -> str:
    """Create the analysis prompt (same as get_ai_analysis in scrape_github.py)"""
    return f"""Analyze this GitHub repository and provide:

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
{repo_content[:8000]}

Format your response EXACTLY as follows (use these exact section headers):

BIOMEDICAL RELEVANCE:
[Your YES/NO answer with explanation]

CODE SUMMARY:
[Your 2-3 sentence summary]

DATA TYPES:
[Your data types list or "Not specified"]

TOOLING:
[Your tools list]"""

def create_batch_requests_file(input_df: pd.DataFrame, output_jsonl: str) -> int:
    """Create a JSONL file with batch requests for all repos with content"""
    logger.info(f"Creating batch requests file: {output_jsonl}")

    requests_count = 0
    with open(output_jsonl, 'w') as f:
        for idx, row in input_df.iterrows():
            content = row.get('Content_For_Analysis', '')

            # Skip rows without content (already analyzed or no content)
            if not content or pd.isna(content) or len(content.strip()) < 50:
                logger.debug(f"Skipping row {idx}: no content or already analyzed")
                continue

            repo_url = row.get('Repository Link', '')
            repo_name = repo_url.split('/')[-1] if repo_url else f"repo_{idx}"

            # Create a valid custom_id (alphanumeric, underscore, hyphen only, max 64 chars)
            custom_id = sanitize_custom_id(f"repo_{idx}_{repo_name}")

            # Create the request
            request = {
                "custom_id": custom_id,
                "params": {
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "temperature": 0.3,
                    "messages": [
                        {
                            "role": "user",
                            "content": create_analysis_prompt(content, repo_name)
                        }
                    ]
                }
            }

            f.write(json.dumps(request) + '\n')
            requests_count += 1

    logger.info(f"Created {requests_count} batch requests")
    return requests_count

def submit_batch(client: Anthropic, requests_file: str) -> str:
    """Submit the batch request file and return batch ID"""
    logger.info(f"Submitting batch request from {requests_file}")

    try:
        # Read and parse JSONL file into list of request dicts
        requests = []
        with open(requests_file, 'r') as f:
            for line in f:
                if line.strip():
                    requests.append(json.loads(line))

        logger.info(f"Loaded {len(requests)} requests from file")

        # Submit batch
        batch = client.messages.batches.create(requests=requests)

        batch_id = batch.id
        logger.info(f"Batch submitted successfully. Batch ID: {batch_id}")
        logger.info(f"Status: {batch.processing_status}")

        return batch_id

    except Exception as e:
        logger.error(f"Failed to submit batch: {str(e)}")
        raise

def poll_batch_status(client: Anthropic, batch_id: str, max_wait_seconds: int = 86400) -> bool:
    """
    Poll batch status until completion or timeout
    max_wait_seconds: default 24 hours (86400 seconds)
    Returns True if completed successfully, False if timeout/error
    """
    logger.info(f"Polling batch status (max wait: {max_wait_seconds/3600:.1f} hours)")

    start_time = time.time()
    poll_interval = 60  # Check every 60 seconds

    while True:
        elapsed = time.time() - start_time

        if elapsed > max_wait_seconds:
            logger.error(f"Timeout: Batch did not complete within {max_wait_seconds/3600:.1f} hours")
            return False

        try:
            batch = client.messages.batches.retrieve(batch_id)
            status = batch.processing_status

            logger.info(f"[{elapsed/60:.1f}m] Status: {status} | "
                       f"Requests: {batch.request_counts.processing} processing, "
                       f"{batch.request_counts.succeeded} succeeded, "
                       f"{batch.request_counts.errored} errored")

            if status == "ended":
                logger.info("Batch processing completed!")
                logger.info(f"Final counts - Succeeded: {batch.request_counts.succeeded}, "
                          f"Errored: {batch.request_counts.errored}, "
                          f"Expired: {batch.request_counts.expired}, "
                          f"Canceled: {batch.request_counts.canceled}")
                return True

            elif status in ["canceling", "canceled"]:
                logger.error(f"Batch was canceled")
                return False

            # Still processing, wait and check again
            time.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Error checking batch status: {str(e)}")
            time.sleep(poll_interval)

def parse_ai_response(response_text: str) -> Dict[str, str]:
    """Parse the AI response into structured fields (same logic as get_ai_analysis)"""
    sections = {
        "biomedical_relevance": "",
        "summary": "",
        "data_types": "",
        "tools": ""
    }

    # Split by section headers
    lines = response_text.split('\n')
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

def download_and_parse_results(client: Anthropic, batch_id: str, output_jsonl: str) -> Dict[str, Dict]:
    """
    Download batch results and parse them
    Returns dict mapping custom_id -> parsed AI analysis
    """
    logger.info(f"Downloading batch results to {output_jsonl}")

    try:
        # Get results iterator
        results = client.messages.batches.results(batch_id)

        parsed_results = {}
        error_count = 0
        success_count = 0

        # Write raw results to file and parse
        with open(output_jsonl, 'w') as f:
            for result in results:
                # Write raw result to file
                f.write(json.dumps(result.to_dict()) + '\n')

                custom_id = result.custom_id

                # Check if request succeeded
                if result.result.type == "succeeded":
                    response_text = result.result.message.content[0].text
                    parsed = parse_ai_response(response_text)
                    parsed_results[custom_id] = parsed
                    success_count += 1
                else:
                    # Handle errors
                    error_type = result.result.type
                    error_msg = f"ERROR - {error_type}"
                    if hasattr(result.result, 'error'):
                        error_msg += f": {result.result.error.message if hasattr(result.result.error, 'message') else str(result.result.error)}"

                    parsed_results[custom_id] = {
                        "biomedical_relevance": error_msg,
                        "summary": "",
                        "data_types": "",
                        "tools": ""
                    }
                    error_count += 1
                    logger.warning(f"Request {custom_id} failed: {error_msg}")

        logger.info(f"Downloaded results: {success_count} succeeded, {error_count} errored")
        return parsed_results

    except Exception as e:
        logger.error(f"Failed to download results: {str(e)}")
        raise

def merge_results_into_dataframe(input_df: pd.DataFrame, parsed_results: Dict[str, Dict]) -> pd.DataFrame:
    """Merge parsed AI results back into the dataframe"""
    logger.info("Merging results into dataframe")

    df = input_df.copy()

    # Ensure AI columns are object dtype (string) to avoid dtype conflicts
    ai_columns = ['Biomedical Relevance', 'Code Summary', 'Data Types', 'Tooling']
    for col in ai_columns:
        if col in df.columns:
            df[col] = df[col].astype('object')

    merged_count = 0

    for idx, row in df.iterrows():
        repo_url = row.get('Repository Link', '')
        repo_name = repo_url.split('/')[-1] if repo_url else f"repo_{idx}"
        custom_id = sanitize_custom_id(f"repo_{idx}_{repo_name}")

        if custom_id in parsed_results:
            analysis = parsed_results[custom_id]
            df.at[idx, 'Biomedical Relevance'] = analysis['biomedical_relevance']
            df.at[idx, 'Code Summary'] = analysis['summary']
            df.at[idx, 'Data Types'] = analysis['data_types']
            df.at[idx, 'Tooling'] = analysis['tools']
            merged_count += 1

    logger.info(f"Merged {merged_count} AI analyses into dataframe")
    return df

def main():
    parser = argparse.ArgumentParser(description='Batch AI analysis for GitHub repositories using Anthropic Batch API')
    parser.add_argument('--input', '-i', required=True,
                       help='Input TSV file from scrape_github.py --batch-call-ai')
    parser.add_argument('--output', '-o', default=None,
                       help='Output TSV file with AI analysis (default: input file with _analyzed suffix)')
    parser.add_argument('--batch-id', '-b', default=None,
                       help='Resume processing with existing batch ID (skip submission)')
    parser.add_argument('--max-wait-hours', '-w', type=float, default=24.0,
                       help='Maximum hours to wait for batch completion (default: 24)')
    parser.add_argument('--anthropic-key', '-a', default=None,
                       help='Anthropic API key (default: from ANTHROPIC_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose (DEBUG) logging')
    parser.add_argument('--log-file', '-l', default=None,
                       help='Log file path (default: batch_ai_analysis_{timestamp}.log)')

    args = parser.parse_args()

    # Setup logger
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_file = args.log_file or get_default_log_file('batch_ai_analysis')
    setup_logger(__name__, log_file, log_level)

    # Check for API key
    anthropic_key = args.anthropic_key or os.getenv('ANTHROPIC_API_KEY')
    if not anthropic_key:
        logger.error("Error: Anthropic API key required. Set ANTHROPIC_API_KEY env var or use --anthropic-key")
        sys.exit(1)

    # Initialize client
    client = Anthropic(api_key=anthropic_key)

    # Generate output filename
    if args.output:
        output_file = args.output
    else:
        base_name = args.input.replace('.tsv', '').replace('.tab', '')
        output_file = f"{base_name}_analyzed.tsv"

    # Generate intermediate file names
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    requests_file = f"batch_requests_{timestamp}.jsonl"
    results_file = f"batch_results_{timestamp}.jsonl"

    try:
        # Read input file
        logger.info(f"Reading input file: {args.input}")
        df = pd.read_csv(args.input, sep='\t')
        logger.info(f"Loaded {len(df)} repositories")

        # Check if Content_For_Analysis column exists
        if 'Content_For_Analysis' not in df.columns:
            logger.error("Error: Input file missing 'Content_For_Analysis' column. "
                        "Did you run scrape_github.py with --batch-call-ai?")
            sys.exit(1)

        # Count repos with content to analyze
        repos_to_analyze = df['Content_For_Analysis'].notna() & (df['Content_For_Analysis'].str.len() >= 50)
        logger.info(f"Repositories with content to analyze: {repos_to_analyze.sum()}")

        if repos_to_analyze.sum() == 0:
            logger.error("No repositories with content to analyze. Nothing to do.")
            sys.exit(1)

        # Submit batch or use existing batch ID
        if args.batch_id:
            logger.info(f"Resuming with existing batch ID: {args.batch_id}")
            batch_id = args.batch_id
        else:
            # Create batch requests file
            num_requests = create_batch_requests_file(df, requests_file)
            logger.info(f"Batch requests file created: {requests_file}")

            # Submit batch
            batch_id = submit_batch(client, requests_file)
            logger.info(f"Batch ID: {batch_id}")
            logger.info(f"You can resume this batch later with: --batch-id {batch_id}")

        # Poll for completion
        max_wait_seconds = int(args.max_wait_hours * 3600)
        success = poll_batch_status(client, batch_id, max_wait_seconds)

        if not success:
            logger.error("Batch did not complete successfully. You can resume later with:")
            logger.error(f"  python batch_ai_analysis.py --input {args.input} --batch-id {batch_id}")
            sys.exit(1)

        # Download and parse results
        parsed_results = download_and_parse_results(client, batch_id, results_file)
        logger.info(f"Batch results saved to: {results_file}")

        # Merge results back into dataframe
        final_df = merge_results_into_dataframe(df, parsed_results)

        # Remove Content_For_Analysis column before saving (it can be large)
        if 'Content_For_Analysis' in final_df.columns:
            final_df = final_df.drop(columns=['Content_For_Analysis'])

        # Save final output
        final_df.to_csv(output_file, sep='\t', index=False)

        logger.info(f"{'='*60}")
        logger.info(f"SUCCESS: Results saved to {output_file}")
        logger.info(f"Total repositories analyzed: {len(parsed_results)}")
        logger.info(f"Batch results (raw): {results_file}")
        logger.info(f"{'='*60}")

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
