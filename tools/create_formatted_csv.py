#!/usr/bin/env python3
"""
Create a formatted CSV with better readability for analysis.
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, Any, List


def create_formatted_csv(jsonl_path: str, csv_path: str) -> None:
    """Create a formatted CSV with better readability."""
    
    # Read JSONL file
    data: List[Dict[str, Any]] = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                data.append(record)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_num}: {e}")
                continue
    
    if not data:
        print("No valid data found in JSONL file")
        return
    
    # Define field order for better readability
    field_order = [
        'id',
        'thread_id', 
        'turn_id',
        'lead',
        'target_agent',
        'prediction',
        'cosine',
        'rougeL', 
        'action_match',
        'entity',
        'style',
        'total'
    ]
    
    # Write formatted CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=field_order)
        writer.writeheader()
        
        for record in data:
            # Create formatted record
            formatted_record = {
                'id': record.get('id', ''),
                'thread_id': record.get('thread_id', ''),
                'turn_id': record.get('turn_id', ''),
                'lead': record.get('lead', '').replace('\n', ' ').replace('\r', ' '),  # Clean newlines
                'target_agent': record.get('target_agent', '').replace('\n', ' ').replace('\r', ' '),
                'prediction': record.get('prediction', '').replace('\n', ' ').replace('\r', ' '),
                'cosine': round(record.get('scores', {}).get('cosine', 0), 4),
                'rougeL': round(record.get('scores', {}).get('rougeL', 0), 4),
                'action_match': record.get('scores', {}).get('action_match', 0),
                'entity': record.get('scores', {}).get('entity', 0),
                'style': round(record.get('scores', {}).get('style', 0), 4),
                'total': round(record.get('scores', {}).get('total', 0), 4)
            }
            
            writer.writerow(formatted_record)
    
    print(f"Created formatted CSV with {len(data)} records: {csv_path}")
    
    # Print summary statistics
    scores = [record.get('scores', {}) for record in data]
    if scores:
        print("\nScore Summary:")
        print(f"Average Total Score: {sum(s.get('total', 0) for s in scores) / len(scores):.4f}")
        print(f"Average Action Match: {sum(s.get('action_match', 0) for s in scores) / len(scores):.4f}")
        print(f"Average Style Score: {sum(s.get('style', 0) for s in scores) / len(scores):.4f}")
        print(f"Average Cosine Similarity: {sum(s.get('cosine', 0) for s in scores) / len(scores):.4f}")


def main():
    """Main function."""
    if len(sys.argv) != 3:
        print("Usage: python create_formatted_csv.py <input.jsonl> <output.csv>")
        print("Example: python create_formatted_csv.py .reports/client_evaluation.jsonl .reports/client_evaluation_formatted.csv")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    # Validate input file exists
    if not Path(input_path).exists():
        print(f"Error: Input file {input_path} does not exist")
        sys.exit(1)
    
    # Create output directory if needed
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    create_formatted_csv(input_path, output_path)


if __name__ == "__main__":
    main()

