#!/usr/bin/env python3
"""
COP Test Results Summarizer

This script processes test results from the COP testing framework 
and generates a condensed summary with key insights.
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import re
from collections import defaultdict, Counter

def extract_metrics(results_dir):
    """Extract metrics from all test results into a DataFrame"""
    metrics_data = []
    results_path = Path(results_dir)
    
    # Walk through results directory
    for model_dir in results_path.glob("*"):
        if not model_dir.is_dir():
            continue
            
        model = model_dir.name
        
        for test_category_dir in model_dir.glob("*"):
            if not test_category_dir.is_dir():
                continue
            
            test_category = test_category_dir.name

            for test_case_dir in test_category_dir.glob("*"):
                if not test_case_dir.is_dir():
                    continue

                test_case = test_case_dir.name
                
                for variant_dir in test_case_dir.glob("*"):
                    if not variant_dir.is_dir():
                        continue
                        
                    variant = variant_dir.name
                    
                    for prompt_type_dir in variant_dir.glob("*"):
                        if not prompt_type_dir.is_dir():
                            continue
                            
                        prompt_type = prompt_type_dir.name
                        metrics_file = prompt_type_dir / "metrics.json"
                        response_file = prompt_type_dir / "response.txt"
                        
                        if metrics_file.exists() and response_file.exists():
                            # Load metrics
                            with open(metrics_file, "r") as f:
                                metrics = json.load(f)
                            
                            # Load response for additional analysis
                            with open(response_file, "r") as f:
                                response = f.read()
                            
                            # Extract additional metrics from response
                            additional_metrics = analyze_response_content(response)
                            
                            # Combine metrics
                            entry = {
                                "model": model,
                                "test_case": test_case,
                                "test_category": test_category,
                                "variant": variant,
                                "prompt_type": prompt_type,
                                **metrics,
                                **additional_metrics
                            }
                            
                            metrics_data.append(entry)
    
    # Convert to DataFrame
    if metrics_data:
        return pd.DataFrame(metrics_data)
    else:
        return pd.DataFrame()

def analyze_response_content(response):
    """Extract additional metrics from response content"""
    metrics = {}
    
    # Count code blocks
    metrics["code_blocks"] = len(re.findall(r"```(?:python)?\n[\s\S]*?\n```", response))
    
    # Check for uncertainty markers
    uncertainty_phrases = [
        "i'm not sure", "i am not sure", "uncertain", "unclear", 
        "cannot determine", "can't determine", "hard to tell",
        "ambiguous", "insufficient information"
    ]
    metrics["uncertainty_markers"] = sum(response.lower().count(phrase) for phrase in uncertainty_phrases)
    
    # Count citation of annotations
    metrics["intent_references"] = response.lower().count("@intent")
    metrics["invariant_references"] = response.lower().count("@invariant")
    metrics["human_decision_references"] = response.lower().count("@human_decision")
    metrics["ai_implement_references"] = response.lower().count("@ai_implement")
    
    # Identify key terms indicating concept understanding
    concept_terms = [
        "purpose", "intent", "invariant", "constraint", "boundary",
        "responsibility", "design", "pattern", "principle", "concept"
    ]
    metrics["concept_term_count"] = sum(response.lower().count(term) for term in concept_terms)
    
    return metrics

def generate_variant_comparison(df):
    """Generate comparison stats between variants"""
    if df.empty:
        return pd.DataFrame()
    
    # Group by test_case, prompt_type, and model
    grouped = df.groupby(["test_case", "prompt_type", "model"])
    
    comparison_rows = []
    
    for (test_case, prompt_type, model), group in grouped:
        # Filter for each variant
        base = group[group["variant"] == "base"]
        cop = group[group["variant"] == "cop"]
        docstring = group[group["variant"] == "docstring"]
        comment = group[group["variant"] == "comment"]
        
        # Skip if any variant is missing
        if len(base) == 0 or len(cop) == 0:
            continue
        
        # Only include docstring/comment if they exist
        has_docstring = len(docstring) > 0
        has_comment = len(comment) > 0
        
        # Get first row for each variant
        base_row = base.iloc[0]
        cop_row = cop.iloc[0]
        docstring_row = docstring.iloc[0] if has_docstring else None
        comment_row = comment.iloc[0] if has_comment else None
        
        # Calculate differences for cop vs base - handling None values
        # Word count comparison
        base_word_count = base_row["word_count"] or 0
        cop_word_count = cop_row["word_count"] or 0
        cop_word_diff = ((cop_word_count / base_word_count) - 1) * 100 if base_word_count > 0 else np.nan
        
        # Execution time comparison - handle None values
        base_exec_time = base_row["execution_time"]
        cop_exec_time = cop_row["execution_time"]
        
        if base_exec_time is not None and cop_exec_time is not None and base_exec_time > 0:
            cop_time_diff = ((cop_exec_time / base_exec_time) - 1) * 100
        else:
            cop_time_diff = np.nan
        
        # Concept term comparison
        base_concept_count = base_row["concept_term_count"] or 0
        cop_concept_count = cop_row["concept_term_count"] or 0
        cop_concept_diff = ((cop_concept_count / base_concept_count) - 1) * 100 if base_concept_count > 0 else np.nan
        
        # Calculate differences for docstring vs base
        if has_docstring:
            docstring_word_count = docstring_row["word_count"] or 0
            docstring_word_diff = ((docstring_word_count / base_word_count) - 1) * 100 if base_word_count > 0 else np.nan
            
            docstring_exec_time = docstring_row["execution_time"]
            if base_exec_time is not None and docstring_exec_time is not None and base_exec_time > 0:
                docstring_time_diff = ((docstring_exec_time / base_exec_time) - 1) * 100
            else:
                docstring_time_diff = np.nan
            
            docstring_concept_count = docstring_row["concept_term_count"] or 0
            docstring_concept_diff = ((docstring_concept_count / base_concept_count) - 1) * 100 if base_concept_count > 0 else np.nan
            
            docstring_uncertainty = docstring_row["uncertainty_markers"] or 0
            base_uncertainty = base_row["uncertainty_markers"] or 0
            docstring_uncertainty_diff = docstring_uncertainty - base_uncertainty
        else:
            docstring_word_diff = np.nan
            docstring_time_diff = np.nan
            docstring_concept_diff = np.nan
            docstring_uncertainty_diff = np.nan
        
        # Calculate differences for comment vs base
        if has_comment:
            comment_word_count = comment_row["word_count"] or 0
            comment_word_diff = ((comment_word_count / base_word_count) - 1) * 100 if base_word_count > 0 else np.nan
            
            comment_exec_time = comment_row["execution_time"]
            if base_exec_time is not None and comment_exec_time is not None and base_exec_time > 0:
                comment_time_diff = ((comment_exec_time / base_exec_time) - 1) * 100
            else:
                comment_time_diff = np.nan
            
            comment_concept_count = comment_row["concept_term_count"] or 0
            comment_concept_diff = ((comment_concept_count / base_concept_count) - 1) * 100 if base_concept_count > 0 else np.nan
            
            comment_uncertainty = comment_row["uncertainty_markers"] or 0
            comment_uncertainty_diff = comment_uncertainty - base_uncertainty
        else:
            comment_word_diff = np.nan
            comment_time_diff = np.nan
            comment_concept_diff = np.nan
            comment_uncertainty_diff = np.nan
        
        # Handle uncertainty for base and cop
        base_uncertainty = base_row["uncertainty_markers"] or 0
        cop_uncertainty = cop_row["uncertainty_markers"] or 0
        cop_uncertainty_diff = cop_uncertainty - base_uncertainty
        
        # Create comparison row
        comparison_rows.append({
            "test_case": test_case,
            "prompt_type": prompt_type,
            "model": model,
            
            # Base metrics
            "base_word_count": base_word_count,
            "base_execution_time": base_exec_time,
            "base_concept_terms": base_concept_count,
            "base_uncertainty": base_uncertainty,
            
            # COP vs Base differences
            "cop_word_diff_pct": cop_word_diff,
            "cop_time_diff_pct": cop_time_diff,
            "cop_concept_diff_pct": cop_concept_diff,
            "cop_uncertainty_diff": cop_uncertainty_diff,
            
            # Docstring vs Base differences
            "docstring_word_diff_pct": docstring_word_diff,
            "docstring_time_diff_pct": docstring_time_diff,
            "docstring_concept_diff_pct": docstring_concept_diff,
            "docstring_uncertainty_diff": docstring_uncertainty_diff,
            
            # Comment vs Base differences
            "comment_word_diff_pct": comment_word_diff,
            "comment_time_diff_pct": comment_time_diff,
            "comment_concept_diff_pct": comment_concept_diff,
            "comment_uncertainty_diff": comment_uncertainty_diff,
            
            # Annotation references in COP responses
            "cop_intent_refs": cop_row["intent_references"] or 0,
            "cop_invariant_refs": cop_row["invariant_references"] or 0,
            "cop_human_decision_refs": cop_row["human_decision_references"] or 0,
            "cop_ai_implement_refs": cop_row["ai_implement_references"] or 0
        })
    
    return pd.DataFrame(comparison_rows)

def generate_summary(df, comparison_df):
    """Generate textual summary of results"""
    if df.empty:
        return "No data available for summary."
    
    summary_parts = []
    
    # Overall metrics
    total_tests = len(df)
    test_cases = df["test_case"].nunique()
    variants = df["variant"].nunique()
    models = df["model"].nunique()
    prompt_types = df["prompt_type"].nunique()
    
    summary_parts.append(f"# COP Testing Results Summary\n")
    summary_parts.append(f"Analysis of {total_tests} test results across {test_cases} test cases, {variants} variants, {models} models, and {prompt_types} prompt types.\n")
    
    # Variant comparison summary
    if not comparison_df.empty:
        # Average differences
        avg_cop_word_diff = comparison_df["cop_word_diff_pct"].mean()
        avg_docstring_word_diff = comparison_df["docstring_word_diff_pct"].mean()
        avg_comment_word_diff = comparison_df["comment_word_diff_pct"].mean()
        
        avg_cop_time_diff = comparison_df["cop_time_diff_pct"].mean()
        avg_docstring_time_diff = comparison_df["docstring_time_diff_pct"].mean()
        avg_comment_time_diff = comparison_df["comment_time_diff_pct"].mean()
        
        avg_cop_concept_diff = comparison_df["cop_concept_diff_pct"].mean()
        avg_docstring_concept_diff = comparison_df["docstring_concept_diff_pct"].mean()
        avg_comment_concept_diff = comparison_df["comment_concept_diff_pct"].mean()
        
        summary_parts.append(f"## Overall Variant Differences\n")
        summary_parts.append(f"### Response Length (word count)\n")
        summary_parts.append(f"- COP vs Base: {avg_cop_word_diff:.1f}%\n")
        summary_parts.append(f"- Docstring vs Base: {avg_docstring_word_diff:.1f}%\n")
        summary_parts.append(f"- Comment vs Base: {avg_comment_word_diff:.1f}%\n\n")
        
        summary_parts.append(f"### Execution Time\n")
        summary_parts.append(f"- COP vs Base: {avg_cop_time_diff:.1f}%\n")
        summary_parts.append(f"- Docstring vs Base: {avg_docstring_time_diff:.1f}%\n")
        summary_parts.append(f"- Comment vs Base: {avg_comment_time_diff:.1f}%\n\n")
        
        summary_parts.append(f"### Concept Term Usage\n")
        summary_parts.append(f"- COP vs Base: {avg_cop_concept_diff:.1f}%\n")
        summary_parts.append(f"- Docstring vs Base: {avg_docstring_concept_diff:.1f}%\n")
        summary_parts.append(f"- Comment vs Base: {avg_comment_concept_diff:.1f}%\n\n")
        
        # Breakdown by test category
        summary_parts.append(f"## Results by Test Category\n")
        
        for category in comparison_df["test_case"].str.split("/").str[0].unique():
            category_df = comparison_df[comparison_df["test_case"].str.startswith(category)]
            
            if not category_df.empty:
                category_avg_cop_word_diff = category_df["cop_word_diff_pct"].mean()
                category_avg_docstring_word_diff = category_df["docstring_word_diff_pct"].mean()
                category_avg_comment_word_diff = category_df["comment_word_diff_pct"].mean()
                
                summary_parts.append(f"### {category.title()}\n")
                summary_parts.append(f"- COP vs Base (words): {category_avg_cop_word_diff:.1f}%\n")
                summary_parts.append(f"- Docstring vs Base (words): {category_avg_docstring_word_diff:.1f}%\n")
                summary_parts.append(f"- Comment vs Base (words): {category_avg_comment_word_diff:.1f}%\n\n")
        
        # Breakdown by prompt type
        summary_parts.append(f"## Results by Prompt Type\n")
        
        for prompt in comparison_df["prompt_type"].unique():
            prompt_df = comparison_df[comparison_df["prompt_type"] == prompt]
            
            if not prompt_df.empty:
                prompt_avg_cop_word_diff = prompt_df["cop_word_diff_pct"].mean()
                prompt_avg_docstring_word_diff = prompt_df["docstring_word_diff_pct"].mean()
                prompt_avg_comment_word_diff = prompt_df["comment_word_diff_pct"].mean()
                
                summary_parts.append(f"### {prompt.replace('_', ' ').title()}\n")
                summary_parts.append(f"- COP vs Base (words): {prompt_avg_cop_word_diff:.1f}%\n")
                summary_parts.append(f"- Docstring vs Base (words): {prompt_avg_docstring_word_diff:.1f}%\n")
                summary_parts.append(f"- Comment vs Base (words): {prompt_avg_comment_word_diff:.1f}%\n\n")
        
        # Annotation references
        avg_intent_refs = comparison_df["cop_intent_refs"].mean()
        avg_invariant_refs = comparison_df["cop_invariant_refs"].mean()
        avg_human_decision_refs = comparison_df["cop_human_decision_refs"].mean()
        avg_ai_implement_refs = comparison_df["cop_ai_implement_refs"].mean()
        
        summary_parts.append(f"## Annotation References in COP Responses\n")
        summary_parts.append(f"- @intent references: {avg_intent_refs:.1f} per response\n")
        summary_parts.append(f"- @invariant references: {avg_invariant_refs:.1f} per response\n")
        summary_parts.append(f"- @human_decision references: {avg_human_decision_refs:.1f} per response\n")
        summary_parts.append(f"- @ai_implement references: {avg_ai_implement_refs:.1f} per response\n\n")
        
        # Largest differences
        top_cop_diff = comparison_df.nlargest(5, "cop_word_diff_pct")
        
        summary_parts.append(f"## Test Cases with Largest COP Impact\n")
        
        for _, row in top_cop_diff.iterrows():
            summary_parts.append(f"- {row['test_case']} ({row['prompt_type']}): {row['cop_word_diff_pct']:.1f}% more words\n")
    
    return "".join(summary_parts)

def generate_visualizations(comparison_df, output_dir):
    """Generate visualizations of key metrics"""
    if comparison_df.empty:
        return
    
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Word count difference by variant
    plt.figure(figsize=(10, 6))
    data = [
        comparison_df["cop_word_diff_pct"].dropna(),
        comparison_df["docstring_word_diff_pct"].dropna(),
        comparison_df["comment_word_diff_pct"].dropna()
    ]
    labels = ['COP', 'Docstring', 'Comment']
    
    plt.boxplot(data, labels=labels)
    plt.title('Response Length Difference vs Base')
    plt.ylabel('Difference (%)')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.savefig(output_dir / "word_diff_boxplot.png", dpi=300, bbox_inches='tight')
    
    # Word count difference by test category
    categories = comparison_df["test_case"].str.split("/").str[0].unique()
    category_cop_diffs = []
    category_docstring_diffs = []
    category_comment_diffs = []
    
    for category in categories:
        category_df = comparison_df[comparison_df["test_case"].str.startswith(category)]
        category_cop_diffs.append(category_df["cop_word_diff_pct"].mean())
        category_docstring_diffs.append(category_df["docstring_word_diff_pct"].mean())
        category_comment_diffs.append(category_df["comment_word_diff_pct"].mean())
    
    plt.figure(figsize=(12, 8))
    x = np.arange(len(categories))
    width = 0.25
    
    plt.bar(x - width, category_cop_diffs, width, label='COP')
    plt.bar(x, category_docstring_diffs, width, label='Docstring')
    plt.bar(x + width, category_comment_diffs, width, label='Comment')
    
    plt.xlabel('Test Category')
    plt.ylabel('Average Word Count Difference (%)')
    plt.title('Impact by Test Category')
    plt.xticks(x, categories)
    plt.legend()
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    plt.savefig(output_dir / "category_impact.png", dpi=300, bbox_inches='tight')
    
    # Word count difference by prompt type
    prompts = comparison_df["prompt_type"].unique()
    prompt_cop_diffs = []
    prompt_docstring_diffs = []
    prompt_comment_diffs = []
    
    for prompt in prompts:
        prompt_df = comparison_df[comparison_df["prompt_type"] == prompt]
        prompt_cop_diffs.append(prompt_df["cop_word_diff_pct"].mean())
        prompt_docstring_diffs.append(prompt_df["docstring_word_diff_pct"].mean())
        prompt_comment_diffs.append(prompt_df["comment_word_diff_pct"].mean())
    
    plt.figure(figsize=(14, 8))
    x = np.arange(len(prompts))
    width = 0.25
    
    plt.bar(x - width, prompt_cop_diffs, width, label='COP')
    plt.bar(x, prompt_docstring_diffs, width, label='Docstring')
    plt.bar(x + width, prompt_comment_diffs, width, label='Comment')
    
    plt.xlabel('Prompt Type')
    plt.ylabel('Average Word Count Difference (%)')
    plt.title('Impact by Prompt Type')
    plt.xticks(x, [p.replace('_', ' ').title() for p in prompts], rotation=45, ha='right')
    plt.legend()
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(output_dir / "prompt_impact.png", dpi=300, bbox_inches='tight')

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Summarize COP test results")
    parser.add_argument("--results-dir", default="results", help="Directory containing test results")
    parser.add_argument("--output-dir", default="summary", help="Directory for summary output")
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Extract metrics
    print("Extracting metrics from test results...")
    df = extract_metrics(args.results_dir)
    
    if df.empty:
        print("No metrics found in results directory!")
        return
    
    # Save full metrics as CSV
    df.to_csv(output_dir / "all_metrics.csv", index=False)
    
    # Generate variant comparison
    print("Generating variant comparisons...")
    comparison_df = generate_variant_comparison(df)
    
    if not comparison_df.empty:
        comparison_df.to_csv(output_dir / "variant_comparison.csv", index=False)
    
    # Generate textual summary
    print("Generating summary...")
    summary = generate_summary(df, comparison_df)
    
    with open(output_dir / "summary.md", "w") as f:
        f.write(summary)
    
    # Generate visualizations
    print("Generating visualizations...")
    generate_visualizations(comparison_df, output_dir / "visualizations")
    
    print(f"Summary generated in {output_dir}")
    print(f"Full summary: {output_dir / 'summary.md'}")

if __name__ == "__main__":
    main()
