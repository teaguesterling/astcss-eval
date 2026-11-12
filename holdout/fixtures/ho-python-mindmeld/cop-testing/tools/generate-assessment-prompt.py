#!/usr/bin/env python3
import os
import json
import glob
from pathlib import Path
import argparse
import sys

def extract_prompt_template(prompt_file_path):
    """Extract just the instruction part of the prompt, before any code listings."""
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Find the first occurrence of "File:" which typically marks the start of code listings
            parts = content.split("File:", 1)
            if len(parts) > 1:
                return parts[0].strip()
            return content.strip()
    except Exception as e:
        return f"Error extracting prompt template: {str(e)}"

def get_input_files(test_dir, variant):
    """Get the input files for a given test case and variant."""
    files = {}
    
    # Look for files matching the patterns
    base_pattern = f"{test_dir}/{variant}.py"
    extra_pattern = f"{test_dir}/{variant}_*.py"
    
    # Add the base file if it exists
    if os.path.exists(base_pattern):
        with open(base_pattern, 'r', encoding='utf-8') as f:
            files[os.path.basename(base_pattern)] = f.read()
    
    # Add any extra files
    for extra_file in glob.glob(extra_pattern):
        with open(extra_file, 'r', encoding='utf-8') as f:
            files[os.path.basename(extra_file)] = f.read()
    
    return files

def get_results(results_dir, test_case, variant, model, prompt_type):
    """Get the results for a given test case, variant, model, and prompt type."""
    # Extract model short name
    model_short = '-'.join(model.split('-')[1:3])
    
    # Construct paths
    result_dir = Path(f"{results_dir}/{model_short}/{test_case}/{variant}/{prompt_type}")
    response_file = result_dir / "response.txt"
    metrics_file = result_dir / "metrics.json"
    prompt_file = result_dir / "prompt.txt"
    
    results = {}
    
    # Get response if it exists
    if response_file.exists():
        with open(response_file, 'r', encoding='utf-8') as f:
            response_content = f.read()
            results['response'] = response_content if response_content else "(empty response)"
    else:
        results['response'] = "(no response file found)"
    
    # Get metrics if they exist
    if metrics_file.exists():
        with open(metrics_file, 'r', encoding='utf-8') as f:
            try:
                results['metrics'] = json.load(f)
            except json.JSONDecodeError:
                results['metrics'] = {"error": "Invalid JSON in metrics file"}
    else:
        results['metrics'] = {"error": "No metrics file found"}
    
    # Get original prompt if it exists
    if prompt_file.exists():
        results['prompt_template'] = extract_prompt_template(prompt_file)
    else:
        results['prompt_template'] = "(prompt file not available)"
    
    return results

def generate_assessment_prompt(results_dir, test_dir, test_case, variants, models, prompt_type):
    """Generate a prompt for assessing the quality of responses."""
    # Background and instructions
    assessment_prompt = f"""# Response Quality Assessment for Concept-Oriented Programming (COP)

## Background
You are evaluating responses from AI assistants to code-related prompts. The code uses different annotation styles:

1. **base**: Standard code with no special annotations
2. **cop**: Code with Concept-Oriented Programming annotations and imported framework
3. **copmin**: COP annotations with minimal explanation in comments
4. **copnone**: COP annotations with no explanation
5. **docstring**: COP annotations embedded in docstrings
6. **comments**: COP annotations in comments

## Research Question
**How do different annotation styles affect the quality, accuracy, and hallucination rate of AI responses?**

Our previous findings indicate a potential "hierarchy of authority" where formal annotations might be interpreted as stronger evidence of functionality than comments or docstrings, potentially increasing hallucination if implementation status isn't explicit.

## Key Issues to Watch For

1. **Hallucination Detection**: Does the response identify when functionality is described but not implemented?
2. **Meta-Distraction**: Does the response focus on analyzing the annotation system rather than using it to understand the code?
3. **Decision Boundary Recognition**: Does the response correctly identify which aspects require human judgment?
4. **Implementation Status Awareness**: Does the response distinguish between intended vs. implemented functionality?
5. **Response Completeness**: Does the response fully address the original query?
6. **Model Differences**: Do different models (Haiku vs. Sonnet) exhibit different behaviors with the same annotations?

## Test Case Information

- **Test Case**: {test_case}
- **Prompt Type**: {prompt_type}
- **Variants**: {', '.join(variants)}
- **Models**: {', '.join(['-'.join(m.split('-')[1:3]) for m in models])}

## Original Prompt Template
"""
    
    # Add the prompt template (should be the same for all variants)
    first_variant = variants[0] if variants else "base"
    first_model = models[0] if models else "claude-3-5-haiku-20241022"
    first_results = get_results(results_dir, test_case, first_variant, first_model, prompt_type)
    assessment_prompt += f"{first_results.get('prompt_template', '(No prompt template available)')}\n\n"
    
    # Add input files section for all variants
    assessment_prompt += "## Input Files\n"
    for variant in variants:
        input_files = get_input_files(test_dir, variant)
        if input_files:
            assessment_prompt += f"\n### {variant.upper()} Variant\n"
            for filename, content in input_files.items():
                # Truncate very long files to avoid exceeding context limits
                if len(content) > 5000:
                    content = content[:5000] + "\n\n... [truncated for brevity] ...\n"
                assessment_prompt += f"\n**File: {filename}**\n```python\n{content}\n```\n"
        else:
            assessment_prompt += f"\n### {variant.upper()} Variant\n"
            assessment_prompt += "No input files found for this variant.\n"
    
    # For each model
    assessment_prompt += "\n## Model Responses\n"
    for model in models:
        model_short = '-'.join(model.split('-')[1:3])
        assessment_prompt += f"\n### Model: {model_short}\n"
        
        # For each variant
        for variant in variants:
            assessment_prompt += f"\n#### Variant: {variant}\n"
            
            # Get the results
            results = get_results(results_dir, test_case, variant, model, prompt_type)
            
            # Add metrics summary (focused on most relevant metrics)
            metrics = results.get('metrics', {})
            
            relevant_metrics = {
                "word_count": metrics.get("word_count", "N/A"),
                "execution_time": metrics.get("execution_time", "N/A"),
                "intent_mentions": metrics.get("intent_mentions", "N/A"),
                "invariant_mentions": metrics.get("invariant_mentions", "N/A"),
                "human_decision_mentions": metrics.get("human_decision_mentions", "N/A"),
                "ai_implement_mentions": metrics.get("ai_implement_mentions", "N/A"),
                "uncertainty_markers": metrics.get("uncertainty_markers", "N/A")
            }
            
            assessment_prompt += "**Metrics**:\n"
            for key, value in relevant_metrics.items():
                assessment_prompt += f"- {key}: {value}\n"
            
            # Add the response (truncate very long responses)
            response = results.get('response', "(no response)")
            if len(response) > 7500:
                response = response[:7500] + "\n\n... [truncated for brevity] ...\n"
            
            assessment_prompt += "\n**Response**:\n"
            assessment_prompt += f"{response}\n"
    
    # Add the evaluation section
    assessment_prompt += """
## Evaluation Requirements

Please provide a thorough assessment following this format:

### 1. Individual Response Assessment

For each model and variant combination:

#### [Model] - [Variant]
- **Accuracy** (1-10): Rate absence of hallucination
- **Completeness** (1-10): Rate how fully it addresses the original query
- **Utility** (1-10): Rate how helpful this would be to a developer
- **Key Strengths**: Identify 2-3 positive aspects
- **Key Weaknesses**: Identify 2-3 issues or shortcomings

### 2. Comparative Analysis

Compare across variants and models to identify patterns:
- How do different annotation styles affect hallucination rates?
- How do models differ in handling the same annotations?
- Which annotation style produces the most accurate responses?
- Which annotation style produces the most useful responses?
- Does adding implementation status information reduce hallucination?

### 3. Quantitative Summary

Provide a table summarizing your scores for each model/variant.

### 4. Recommendations

Based on your analysis, what modifications to the COP framework would most improve response quality?

Your assessment should be evidence-based, citing specific examples from the responses to support your conclusions.

Only use information provided in this prompt. It should contain all relevant information needed to answer this request. Do not interrogate other files or execute commands.
"""
    
    return assessment_prompt

def main():
    parser = argparse.ArgumentParser(description="Generate assessment prompts for response quality evaluation")
    parser.add_argument("--results_dir", default="results", help="Directory containing test results")
    parser.add_argument("--test_dir", default="test_cases", help="Directory containing test case files")
    parser.add_argument("--test_case", required=True, help="Test case to evaluate (e.g., 'hallucination/missing_implementation')")
    parser.add_argument("--prompt_type", required=True, help="Prompt type to evaluate (e.g., 'understanding')")
    parser.add_argument("--variants", nargs="+", default=["base", "cop", "copmin", "copnone", "docstring", "comments"], 
                        help="Variants to evaluate")
    parser.add_argument("--models", nargs="+", default=["claude-3-5-haiku-20241022", "claude-3-7-sonnet-20250219"], 
                        help="Models to evaluate")
    parser.add_argument("--output_file", help="Optional file to write output to")
    
    args = parser.parse_args()
    
    # Filter to only include variants that exist
    existing_variants = []
    for variant in args.variants:
        test_path = os.path.join(args.test_dir, args.test_case, f"{variant}.py")
        if os.path.exists(test_path):
            existing_variants.append(variant)
        else:
            print(f"Warning: Variant {variant} not found at {test_path}", file=sys.stderr)
    
    if not existing_variants:
        print(f"Error: No valid variants found for test case {args.test_case}", file=sys.stderr)
        return
    
    # Generate the assessment prompt
    assessment_prompt = generate_assessment_prompt(
        args.results_dir, 
        os.path.join(args.test_dir, args.test_case),
        args.test_case, 
        existing_variants, 
        args.models, 
        args.prompt_type
    )
    
    # Output to file or stdout
    if args.output_file:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(assessment_prompt)
        print(f"Assessment prompt written to {args.output_file}", file=sys.stderr)
    else:
        print(assessment_prompt)
    
if __name__ == "__main__":
    main()
