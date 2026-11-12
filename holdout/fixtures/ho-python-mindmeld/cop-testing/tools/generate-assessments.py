#!/usr/bin/env python3
import os
import argparse
import subprocess
import glob
from pathlib import Path
import json
import re

def discover_test_combinations(results_dir, test_dir, 
                               filter_test_cases=None, 
                               filter_prompt_types=None, 
                               filter_models=None,
                               include_variants=None,
                               min_variants=2):
    """
    Discover all test case, prompt type, and model combinations in results directory.
    Returns a list of dicts, each containing test_case, prompt_type, models, and variants.
    """
    combinations = []
    
    # First pass: find all unique test cases
    model_dirs = [d for d in os.listdir(results_dir) if os.path.isdir(os.path.join(results_dir, d))]
    all_tests = set()
    
    for model_dir in model_dirs:
        model_path = os.path.join(results_dir, model_dir)
        test_categories = [d for d in os.listdir(model_path) if os.path.isdir(os.path.join(model_path, d))]
        
        for category in test_categories:
            category_path = os.path.join(model_path, category)
            test_cases = [d for d in os.listdir(category_path) if os.path.isdir(os.path.join(category_path, d))]
            
            for test_case in test_cases:
                full_test_case = f"{category}/{test_case}"
                all_tests.add(full_test_case)
    
    # Apply test case filter if specified
    if filter_test_cases:
        filtered_tests = set()
        for pattern in filter_test_cases:
            for test in all_tests:
                if re.search(pattern, test):
                    filtered_tests.add(test)
        all_tests = filtered_tests
    
    # Second pass: for each test, find all prompt types, models, and variants
    for test_case in all_tests:
        # Find all prompt types for this test
        all_prompt_types = set()
        all_models = {}  # Dict of model_dir -> full_model_name
        
        for model_dir in model_dirs:
            test_path = os.path.join(results_dir, model_dir, test_case)
            if not os.path.exists(test_path):
                continue
            
            # Try to determine full model name
            metadata_files = glob.glob(f"{test_path}/*/*/metadata.json")
            for metadata_file in metadata_files:
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        if 'model' in metadata:
                            all_models[model_dir] = metadata['model']
                            break
                except:
                    pass
            
            # If we couldn't find it, use a default pattern
            if model_dir not in all_models:
                # Try to reconstruct model name from directory name (e.g., "3-5" -> "claude-3-5-haiku-20241022")
                if model_dir.startswith("3-5"):
                    all_models[model_dir] = "claude-3-5-haiku-20241022"
                elif model_dir.startswith("3-7"):
                    all_models[model_dir] = "claude-3-7-sonnet-20250219"
                else:
                    all_models[model_dir] = f"claude-{model_dir}"
            
            # Find all variants and prompt types
            variants = [d for d in os.listdir(test_path) if os.path.isdir(os.path.join(test_path, d))]
            
            for variant in variants:
                variant_path = os.path.join(test_path, variant)
                prompt_types = [d for d in os.listdir(variant_path) if os.path.isdir(os.path.join(variant_path, d))]
                all_prompt_types.update(prompt_types)
        
        # Apply prompt type filter if specified
        if filter_prompt_types:
            filtered_prompt_types = set()
            for pattern in filter_prompt_types:
                for prompt_type in all_prompt_types:
                    if re.search(pattern, prompt_type):
                        filtered_prompt_types.add(prompt_type)
            all_prompt_types = filtered_prompt_types
        
        # Apply model filter if specified
        if filter_models:
            filtered_models = {}
            for pattern in filter_models:
                for model_dir, model_name in all_models.items():
                    if re.search(pattern, model_name) or re.search(pattern, model_dir):
                        filtered_models[model_dir] = model_name
            all_models = filtered_models
        
        # For each prompt type, find all valid variants across models
        for prompt_type in all_prompt_types:
            all_variants = set()
            
            for model_dir in all_models:
                variant_dirs = glob.glob(f"{results_dir}/{model_dir}/{test_case}/*/")
                for variant_dir in variant_dirs:
                    variant = os.path.basename(os.path.dirname(variant_dir))
                    prompt_path = os.path.join(variant_dir, prompt_type)
                    if os.path.exists(prompt_path):
                        if include_variants is None or variant in include_variants:
                            all_variants.add(variant)
            
            # Only include combinations with at least min_variants variants
            if len(all_variants) >= min_variants:
                combinations.append({
                    'test_case': test_case,
                    'prompt_type': prompt_type,
                    'models': list(all_models.values()),
                    'variants': list(all_variants)
                })
    
    return combinations

def generate_assessment(combination, results_dir, test_dir, output_dir, 
                        claude_path=None, prompter_path=None, assessment_model=None):
    """Generate assessment for a specific combination."""
    test_case = combination['test_case']
    prompt_type = combination['prompt_type']
    models = combination['models']
    variants = combination['variants']
    
    # Create sanitized filename
    sanitized_test_case = test_case.replace('/', '_')
    output_filename = f"{sanitized_test_case}_{prompt_type}_assessment.txt"
    output_path = os.path.join(output_dir, output_filename)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    if prompter_path is None:
        prompter_path = os.path.join(os.path.dirname(__file__), "generate-assessment-prompt.py")
    
    # Build command
    cmd = [
        "python3", prompter_path,
        "--results_dir", results_dir,
        "--test_dir", test_dir,
        "--test_case", test_case,
        "--prompt_type", prompt_type,
        "--variants", *variants,
        "--models", *models,
        "--output_file", output_path
    ]

    # Run the command
    print(f"Generating assessment for {test_case} - {prompt_type}...")
    try:
        subprocess.run(cmd, check=True)
        print(f"  Assessment saved to: {output_path}")
        
        # If claude_path is provided, run through Claude
        if claude_path:
            claude_output = f"{output_path}.response.md"
            
            # Read the prompt file
            with open(output_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read()
            
            # Set up environment for Claude
            env = os.environ.copy()
            if assessment_model is not None:
                env["ANTHROPIC_MODEL"] = assessment_model
            
            # Run Claude with stdin/stdout
            print(f"  Running through Claude (model: {env.get('ANTHROPIC_MODEL', 'default')})")
            
            try:
                # Run Claude with the prompt as stdin
                process = subprocess.Popen(
                    [claude_path, '--print'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env
                )
                
                # Send prompt and get response
                stdout, stderr = process.communicate(input=prompt_content)
                
                # Check for errors
                if process.returncode != 0:
                    print(f"  Claude error: {stderr}")
                    return None
                
                # Write response to file
                with open(claude_output, 'w', encoding='utf-8') as f:
                    f.write(stdout)
                
                print(f"  Claude response saved to: {claude_output}")
                return claude_output
            except Exception as e:
                print(f"  Error running Claude: {e}")
                return None
        
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  Error generating assessment: {e}")
        return None
    

def main():
    parser = argparse.ArgumentParser(description="Run assessment generator on all test results")
    parser.add_argument("--results_dir", default="results", help="Directory containing test results")
    parser.add_argument("--test_dir", default="test_cases", help="Directory containing test case files")
    parser.add_argument("--output_dir", default="assessments", help="Directory to store assessment prompts")
    parser.add_argument("--filter_test_cases", nargs="*", help="Filter test cases by regex pattern")
    parser.add_argument("--filter_prompt_types", nargs="*", help="Filter prompt types by regex pattern")
    parser.add_argument("--filter_models", nargs="*", help="Filter models by regex pattern")
    parser.add_argument("--include_variants", nargs="*", help="Include only variants provided")
    parser.add_argument("--min_variants", type=int, default=2, help="Minimum number of variants to include")
    parser.add_argument("--assessment_model", default="claude-3-7-sonnet-20250219", help="Claude model to use in assessment")
    parser.add_argument("--claude_path", help="Path to Claude CLI to run assessments automatically")
    parser.add_argument("--prompter_path", help="Path to Claude CLI to run assessments automatically")
    parser.add_argument("--limit", type=int, help="Limit number of assessments to generate")
    
    args = parser.parse_args()
    
    # Discover all test combinations
    combinations = discover_test_combinations(
        args.results_dir, 
        args.test_dir,
        args.filter_test_cases,
        args.filter_prompt_types,
        args.filter_models,
        args.include_variants,
        args.min_variants
    )
    
    # Limit if specified
    if args.limit and args.limit > 0:
        combinations = combinations[:args.limit]
    
    print(f"Found {len(combinations)} test combinations to assess")
    
    # Generate assessments for each combination
    results = []
    for i, combination in enumerate(combinations, 1):
        print(f"\n{i}/{len(combinations)}: Processing {combination['test_case']} - {combination['prompt_type']}")
        print(f"  Models: {', '.join(['-'.join(m.split('-')[1:3]) for m in combination['models']])}")
        print(f"  Variants: {', '.join(combination['variants'])}")
        
        result = generate_assessment(
            combination,
            args.results_dir,
            args.test_dir,
            args.output_dir,
            args.claude_path,
            args.prompter_path,
            args.assessment_model,
        )
        
        if result:
            results.append({
                'test_case': combination['test_case'],
                'prompt_type': combination['prompt_type'],
                'output_file': result
            })
    
    # Print summary
    print(f"\nGenerated {len(results)} assessments in {args.output_dir}")
    
if __name__ == "__main__":
    main()
