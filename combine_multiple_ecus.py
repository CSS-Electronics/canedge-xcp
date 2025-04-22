import argparse
import json
from pathlib import Path

MAX_FRAMES = 224
MAX_DATA_BYTES = 4096

def load_transmit_list(json_path):
    with open(json_path, "r") as f:
        data = json.load(f)
    return data["can_1"]["transmit"]

def save_transmit_list(transmit_list, output_path):
    output_data = {
        "can_1": {
            "transmit": transmit_list
        }
    }
    output_path = output_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"\nMerged transmit list saved to: {output_path}")

def get_max_delay(transmit_list):
    if not transmit_list:
        return 0
    return max(frame["delay"] for frame in transmit_list)

def get_can_ids(transmit_list):
    return set(frame["id"] for frame in transmit_list)

def merge_transmit_lists(input_files, offset_delta, output_path):
    merged_list = []
    current_offset = 0
    all_can_ids = set()

    for idx, file_path in enumerate(input_files):
        frames = load_transmit_list(file_path)

        # Extract CAN IDs and check for duplicates
        can_ids = get_can_ids(frames)
        overlap_ids = all_can_ids.intersection(can_ids)
        if overlap_ids:
            print(f"Warning: Overlapping CAN IDs found in {file_path.name}: {overlap_ids}")
        all_can_ids.update(can_ids)

        # Offset delay for current set of frames
        for frame in frames:
            frame = frame.copy()
            frame["delay"] += current_offset
            merged_list.append(frame)

        max_delay = get_max_delay(frames)
        current_offset += max_delay + offset_delta

    # Validation: Frame count
    if len(merged_list) > MAX_FRAMES:
        print(f"Warning: Total frames = {len(merged_list)} > max allowed = {MAX_FRAMES}")

    # Validation: Total data bytes
    total_bytes = sum(len(f["data"]) // 2 for f in merged_list)
    if total_bytes > MAX_DATA_BYTES:
        print(f"Warning: Total data bytes = {total_bytes} > max allowed = {MAX_DATA_BYTES}")

    save_transmit_list(merged_list, output_path)

def parse_args():
    parser = argparse.ArgumentParser(description="Merge XCP transmit lists with offset adjustment")
    parser.add_argument("output_transmit_merged", type=Path, help="Path to merged output transmit list JSON")
    parser.add_argument("--input_transmit_files", type=Path, nargs="+", required=True, help="Paths to individual transmit list JSON files")
    parser.add_argument("--offset_delta", type=int, default=500, help="Delay in ms between merged lists (default: 500)")
    args = parser.parse_args()

    # Ensure all paths are absolute based on current working directory
    args.output_transmit_merged = args.output_transmit_merged.resolve()
    args.input_transmit_files = [p.resolve() for p in args.input_transmit_files]

    return args


if __name__ == "__main__":
    args = parse_args()
    merge_transmit_lists(args.input_transmit_files, args.offset_delta, args.output_transmit_merged)
