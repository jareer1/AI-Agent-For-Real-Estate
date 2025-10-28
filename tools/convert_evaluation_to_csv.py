#!/usr/bin/env python3
"""
Convert client_evaluation.jsonl to CSV format for easier analysis.
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, Any, List


def convert_jsonl_to_csv(jsonl_path: str, csv_path: str) -> None:
    """Convert JSONL evaluation file to CSV format."""
    
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
    
    # Extract all possible field names
    all_fields = set()
    for record in data:
        all_fields.update(record.keys())
    
    # Flatten nested scores dict
    flattened_fields = []
    for field in sorted(all_fields):
        if field == 'scores':
            # Add individual score fields
            flattened_fields.extend(['cosine', 'rougeL', 'action_match', 'entity', 'style', 'total'])
        else:
            flattened_fields.append(field)
    
    # Write CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=flattened_fields)
        writer.writeheader()
        
        for record in data:
            # Flatten the record
            flattened_record = {}
            for field in flattened_fields:
                if field in ['cosine', 'rougeL', 'action_match', 'entity', 'style', 'total']:
                    # Extract from scores dict
                    flattened_record[field] = record.get('scores', {}).get(field, '')
                else:
                    flattened_record[field] = record.get(field, '')
            
            writer.writerow(flattened_record)
    
    print(f"Converted {len(data)} records from {jsonl_path} to {csv_path}")
    print(f"CSV columns: {', '.join(flattened_fields)}")


def main():
    """Main function."""
    if len(sys.argv) != 3:
        print("Usage: python convert_evaluation_to_csv.py <input.jsonl> <output.csv>")
        print("Example: python convert_evaluation_to_csv.py .reports/client_evaluation.jsonl .reports/client_evaluation.csv")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    # Validate input file exists
    if not Path(input_path).exists():
        print(f"Error: Input file {input_path} does not exist")
        sys.exit(1)
    
    # Create output directory if needed
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    convert_jsonl_to_csv(input_path, output_path)


if __name__ == "__main__":
    main()

