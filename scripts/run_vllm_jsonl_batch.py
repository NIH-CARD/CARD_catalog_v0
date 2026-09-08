#!/usr/bin/env python3
"""
Run a pre-built OpenAI-Batch-format JSONL file of prompts against a live vLLM
server (the /v1/responses endpoint), concurrently.

Unlike the OpenAI/Portkey/Anthropic Batch APIs, vLLM's `vllm serve` doesn't
expose a /v1/batches endpoint -- it only serves live requests. This script is
the client-side substitute: it fires each request concurrently so vLLM's
continuous batching does the actual GPU-level batching.

Each input line is expected in the shape already produced by
BatchRequestBuilder.create_openai_request:
    {"custom_id": ..., "method": "POST", "url": "/v1/responses",
     "body": {"model": ..., "input": [...], "text": {...}}, "metadata": {...}}

Resuming: on restart, any custom_id with a successful (non-error) line already
in --output is skipped; previously-errored requests are retried, since errors
here are usually transient (dropped port-forward, momentary server hiccup),
not permanent per-document failures.

Usage:
    kubectl port-forward -n data-gatherer svc/vllm-gptoss 8000:8000 &
    python scripts/run_vllm_jsonl_batch.py \\
        --input /path/to/fulltext_batch_1.jsonl \\
        --output /path/to/fulltext_batch_1_results.jsonl \\
        --concurrency 8
"""

import argparse
import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_gatherer.llm.batch_storage import BatchStorageManager
from data_gatherer.env import VLLM_CLIENT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_completed(output_path):
    """Successful custom_ids already in the output file (to skip), and the successful
    lines themselves (to keep) - error lines are dropped so retries don't leave stale
    duplicate entries behind for the same custom_id."""
    if not Path(output_path).exists():
        return set(), []
    done = set()
    kept_lines = []
    with open(output_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if 'error' not in record:
                done.add(record['custom_id'])
                kept_lines.append(line)
    return done, kept_lines


def run_one(client, request, max_output_tokens, timeout):
    custom_id = request['custom_id']
    body = request['body']
    try:
        response = client.responses.create(
            model=body['model'],
            input=body['input'],
            max_output_tokens=body.get('max_output_tokens', max_output_tokens),
            timeout=timeout,
            **({'text': body['text']} if 'text' in body else {}),
        )
        if response.status == 'incomplete':
            # gpt-oss-20b is a reasoning model - its hidden chain-of-thought counts against
            # max_output_tokens same as the final message, so a truncation here often means
            # reasoning ate the whole budget before any message was produced, leaving
            # output_text empty. Treat as an error so it's retried on rerun instead of
            # silently persisting as a hollow "success".
            reason = getattr(response.incomplete_details, 'reason', None) if response.incomplete_details else None
            raise RuntimeError(f"response incomplete (reason={reason}), output_text={response.output_text!r}")
        return {
            'custom_id': custom_id,
            'metadata': request.get('metadata'),
            'output_text': response.output_text,
        }
    except Exception as e:
        logger.warning(f"Request {custom_id} failed: {e}")
        return {
            'custom_id': custom_id,
            'metadata': request.get('metadata'),
            'error': str(e),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', required=True, help='Input JSONL file of batch requests')
    parser.add_argument('--output', required=True, help='Output JSONL file for results')
    parser.add_argument('--base-url', default=VLLM_CLIENT, help='vLLM OpenAI-compatible base URL (default: VLLM_CLIENT env var)')
    parser.add_argument('--concurrency', type=int, default=8, help='Number of concurrent in-flight requests')
    parser.add_argument('--max-output-tokens', type=int, default=4096, help='Fallback max_output_tokens if not set per-request - gpt-oss-20b is a reasoning model, its hidden chain-of-thought counts against this budget too')
    parser.add_argument('--timeout', type=float, default=180.0, help='Per-request timeout in seconds (default: 180)')
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N unprocessed requests (for testing)')
    args = parser.parse_args()

    if not args.base_url:
        parser.error('--base-url not given and VLLM_CLIENT env var is not set')

    storage = BatchStorageManager(logger=logger)
    requests = storage.read_jsonl_batch_file(args.input)

    done, kept_lines = load_completed(args.output)
    if Path(args.output).exists():
        # Always rewrite down to just kept_lines, even when that's empty (e.g. every
        # prior line was an error) - `if kept_lines:` skipped this exact case, leaving
        # stale error lines on disk for append mode to duplicate underneath fresh results.
        with open(args.output, 'w', encoding='utf-8') as out_f:
            out_f.writelines(kept_lines)

    pending = [r for r in requests if r['custom_id'] not in done]
    if args.limit:
        pending = pending[:args.limit]

    logger.info(f"{len(requests)} total requests, {len(done)} already done, {len(pending)} to process against {args.base_url}")

    client = OpenAI(base_url=args.base_url, api_key="not-needed", timeout=args.timeout)
    write_lock = threading.Lock()
    completed = 0
    n_errors = 0

    with open(args.output, 'a', encoding='utf-8') as out_f, ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_one, client, r, args.max_output_tokens, args.timeout): r['custom_id'] for r in pending}
        for future in as_completed(futures):
            result = future.result()
            if 'error' in result:
                n_errors += 1
            with write_lock:
                out_f.write(json.dumps(result, ensure_ascii=False) + '\n')
                out_f.flush()
            completed += 1
            if completed % 25 == 0 or completed == len(pending):
                logger.info(f"{completed}/{len(pending)} done ({n_errors} error(s) so far)")

    logger.info(f"Finished. {completed - n_errors} succeeded, {n_errors} errored. Results written to {args.output}")


if __name__ == '__main__':
    main()
