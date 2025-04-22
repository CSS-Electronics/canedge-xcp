import json
import argparse
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("Missing dependency 'jsonschema'. Install it via pip: pip install jsonschema")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inject XCP transmit list into CANedge configuration"
    )
    parser.add_argument("input_transmit_file", type=Path, help="Path to the transmit list JSON file")
    parser.add_argument("input_config_file", type=Path, help="Path to the existing config JSON file")
    parser.add_argument("schema_validate", choices=["true", "false"], help="Whether to validate with a schema")

    parser.add_argument("--input_schema_file", type=Path, help="Path to the JSON Schema file (required if validation is true)")
    parser.add_argument("--can_channel", choices=["can1", "can2"], default="can1", help="CAN channel to insert into (default: can1)")

    return parser.parse_args()


def main():
    args = parse_args()

    can_key = f"can_{1 if args.can_channel == 'can1' else 2}"

    # Load input files
    with args.input_config_file.open("r", encoding="utf-8") as f:
        config_data = json.load(f)

    with args.input_transmit_file.open("r", encoding="utf-8") as f:
        partial_data = json.load(f)

    # Inject transmit list
    transmit_data = partial_data.get("can_1", {}).get("transmit", [])
    if not isinstance(transmit_data, list):
        print("Error: Transmit data is not a list.")
        sys.exit(1)

    config_data.setdefault(can_key, {})["transmit"] = transmit_data

    # Validate against schema if required
    if args.schema_validate == "true":
        if not args.input_schema_file:
            print("Validation is enabled but no Rule Schema JSON file was provided.")
            sys.exit(1)

        with args.input_schema_file.open("r", encoding="utf-8") as f:
            schema = json.load(f)

        try:
            jsonschema.validate(instance=config_data, schema=schema)
            print("Schema validation passed.")
        except jsonschema.ValidationError as e:
            print(f"Schema validation failed: {e.message}")
            sys.exit(1)

    # Save updated config back to file (overwrite original)
    with args.input_config_file.open("w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    print(f"Transmit list injected into '{can_key}' and saved to {args.input_config_file}")


if __name__ == "__main__":
    main()
