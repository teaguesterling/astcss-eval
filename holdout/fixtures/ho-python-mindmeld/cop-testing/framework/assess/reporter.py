import json
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

class TestReporter:
    def __init__(self, config):
        self.config = config
        self.results_dir = Path(config.RESULTS_DIR)

    def generate_reports(self):
        """Generate comprehensive reports from test results"""
        # Collect all metrics
        metrics_data = self._collect_metrics()
        
        if not metrics_data:
            print("No metrics data found. Skipping report generation.")
            return
        
        # Generate comparison tables
        self._generate_comparison_tables(metrics_data)
        
        # Generate visualization charts
        self._generate_charts(metrics_data)
        
        # Generate summary report
        self._generate_summary_report(metrics_data)
        
    def _collect_metrics(self):
        """Collect metrics from all test results"""
        metrics_data = []
        
        print(f"Looking for metrics in: {self.results_dir}")
        
        if not self.results_dir.exists():
            print(f"Results directory not found: {self.results_dir}")
            return metrics_data
        
        # Debug: List directories
        print("Available model directories:")
        for dir in self.results_dir.glob("*"):
            if dir.is_dir():
                print(f"  - {dir.name}")
        
        for model_dir in self.results_dir.glob("*"):
            if not model_dir.is_dir():
                continue
                
            model = model_dir.name
            print(f"Checking model: {model}")
            
            for test_category_dir in model_dir.glob("*"):
                if not test_category_dir.is_dir():
                    continue

                test_category = test_category_dir.name

                for test_case_dir in test_category_dir.glob("*"):
                    if not test_case_dir.is_dir():
                        continue 
                    
                    test_case = test_case_dir.name
                    print(f"  Checking test case: {test_case} [{test_category}]")
                    
                    for variant_dir in test_case_dir.glob("*"):
                        if not variant_dir.is_dir():
                            continue
                            
                        variant = variant_dir.name
                        print(f"    Checking variant: {variant}")
                        
                        for prompt_type_dir in variant_dir.glob("*"):
                            if not prompt_type_dir.is_dir():
                                continue
                                
                            prompt_type = prompt_type_dir.name
                            metrics_file = prompt_type_dir / "metrics.json"
                            print(f"      Checking for metrics: {metrics_file}")
                            
                            if metrics_file.exists():
                                print(f"      Found metrics file")
                                try:
                                    with open(metrics_file, "r") as f:
                                        metrics = json.load(f)
                                        
                                    metrics_data.append({
                                        "model": model,
                                        "test_case": test_case,
                                        "variant": variant,
                                        "prompt_type": prompt_type,
                                        **metrics
                                    })
                                except Exception as e:
                                    print(f"      Error reading metrics: {e}")
                            else:
                                print(f"      Metrics file not found")
        
        print(f"Collected {len(metrics_data)} metrics records")
        return metrics_data
    
    def _generate_comparison_tables(self, metrics_data):
        """Generate comparison tables between base and COP variants"""
        if not metrics_data:
            print("No metrics data for comparison tables. Skipping.")
            return
        df = pd.DataFrame(metrics_data)
        
        # Create directory for reports
        reports_dir = self.results_dir / "reports"
        reports_dir.mkdir(exist_ok=True)
        
        # Group by model, test_case, and prompt_type
        grouped = df.groupby(["model", "test_case", "prompt_type"])
        
        comparison_rows = []
        
        for (model, test_case, prompt_type), group in grouped:
            base_row = group[group["variant"] == "base"]
            cop_row = group[group["variant"] == "cop"]
            
            if len(base_row) == 0 or len(cop_row) == 0:
                continue
                
            base_metrics = base_row.iloc[0]
            cop_metrics = cop_row.iloc[0]
            
            # Calculate differences
            word_count_diff = cop_metrics["word_count"] - base_metrics["word_count"]
            word_count_diff_pct = (word_count_diff / base_metrics["word_count"]) * 100 if base_metrics["word_count"] > 0 else float('nan')
            
            execution_time_diff = cop_metrics["execution_time"] - base_metrics["execution_time"] if cop_metrics["execution_time"] and base_metrics["execution_time"] else None
            execution_time_diff_pct = (execution_time_diff / base_metrics["execution_time"]) * 100 if execution_time_diff is not None and base_metrics["execution_time"] > 0 else float('nan')
            
            comparison_rows.append({
                "model": model,
                "test_case": test_case,
                "prompt_type": prompt_type,
                "base_word_count": base_metrics["word_count"],
                "cop_word_count": cop_metrics["word_count"],
                "word_count_diff": word_count_diff,
                "word_count_diff_pct": word_count_diff_pct,
                "base_execution_time": base_metrics["execution_time"],
                "cop_execution_time": cop_metrics["execution_time"],
                "execution_time_diff": execution_time_diff,
                "execution_time_diff_pct": execution_time_diff_pct,
                "base_intent_mentions": base_metrics["intent_mentions"],
                "cop_intent_mentions": cop_metrics["intent_mentions"],
                "base_invariant_mentions": base_metrics["invariant_mentions"],
                "cop_invariant_mentions": cop_metrics["invariant_mentions"],
                "base_human_decision_mentions": base_metrics["human_decision_mentions"],
                "cop_human_decision_mentions": cop_metrics["human_decision_mentions"],
                "base_factual_accuracy": base_metrics.get("factual_accuracy", float('nan')),
                "cop_factual_accuracy": cop_metrics.get("factual_accuracy", float('nan')),
            })
            
        comparison_df = pd.DataFrame(comparison_rows)
        comparison_df.to_csv(reports_dir / "comparison_table.csv", index=False)
        
        # Generate HTML table
        html_table = comparison_df.to_html()
        with open(reports_dir / "comparison_table.html", "w") as f:
            f.write(html_table)
            
    def _generate_charts(self, metrics_data):
        """Generate visualization charts"""
        if not metrics_data:
            print("No metrics data for comparison tables. Skipping.")
            return
        df = pd.DataFrame(metrics_data)
        
        # Create directory for charts
        charts_dir = self.results_dir / "reports" / "charts"
        charts_dir.mkdir(exist_ok=True, parents=True)
        
        # Word count comparison by test case and variant
        plt.figure(figsize=(12, 8))
        avg_word_counts = df.groupby(["test_case", "variant"])["word_count"].mean().unstack()
        avg_word_counts.plot(kind="bar")
        plt.title("Average Word Count by Test Case and Variant")
        plt.ylabel("Word Count")
        plt.xlabel("Test Case")
        plt.tight_layout()
        plt.savefig(charts_dir / "word_count_comparison.png")
        
        # Execution time comparison
        plt.figure(figsize=(12, 8))
        avg_exec_times = df.groupby(["test_case", "variant"])["execution_time"].mean().unstack()
        avg_exec_times.plot(kind="bar")
        plt.title("Average Execution Time by Test Case and Variant")
        plt.ylabel("Execution Time (s)")
        plt.xlabel("Test Case")
        plt.tight_layout()
        plt.savefig(charts_dir / "execution_time_comparison.png")
        
        # Annotation mentions
        plt.figure(figsize=(12, 8))
        annotation_cols = ["intent_mentions", "invariant_mentions", "human_decision_mentions", "ai_implement_mentions"]
        cop_annotations = df[df["variant"] == "cop"][["test_case"] + annotation_cols].groupby("test_case").mean()
        cop_annotations.plot(kind="bar")
        plt.title("COP Annotation Mentions by Test Case")
        plt.ylabel("Average Mentions")
        plt.xlabel("Test Case")
        plt.tight_layout()
        plt.savefig(charts_dir / "annotation_mentions.png")
        
    def _generate_summary_report(self, metrics_data):
        """Generate a summary report"""
        if not metrics_data:
            print("No metrics data for comparison tables. Skipping.")
            return
        df = pd.DataFrame(metrics_data)
        
        # Create directory for reports
        reports_dir = self.results_dir / "reports"
        
        # Calculate overall metrics
        overall_metrics = {
            "total_tests": len(df),
            "total_base_tests": len(df[df["variant"] == "base"]),
            "total_cop_tests": len(df[df["variant"] == "cop"]),
            "avg_word_count_diff_pct": df.groupby(["model", "test_case", "prompt_type"]).apply(
                lambda g: (g[g["variant"] == "cop"]["word_count"].values[0] - g[g["variant"] == "base"]["word_count"].values[0]) / g[g["variant"] == "base"]["word_count"].values[0] * 100 
                if len(g[g["variant"] == "cop"]) > 0 and len(g[g["variant"] == "base"]) > 0 and g[g["variant"] == "base"]["word_count"].values[0] > 0 
                else float('nan')
            ).mean(),
            "avg_execution_time_diff_pct": df.groupby(["model", "test_case", "prompt_type"]).apply(
                lambda g: (g[g["variant"] == "cop"]["execution_time"].values[0] - g[g["variant"] == "base"]["execution_time"].values[0]) / g[g["variant"] == "base"]["execution_time"].values[0] * 100 
                if (len(g[g["variant"] == "cop"]) > 0 and 
                    len(g[g["variant"] == "base"]) > 0 and 
                    g[g["variant"] == "base"]["execution_time"].values[0] is not None and
                    g[g["variant"] == "cop"]["execution_time"].values[0] is not None and
                    g[g["variant"] == "base"]["execution_time"].values[0] > 0)
                else float('nan')
            ).mean()
        }
        
        # Generate summary report
        with open(reports_dir / "summary_report.md", "w") as f:
            f.write("# COP Testing Summary Report\n\n")
            f.write(f"Total tests: {overall_metrics['total_tests']}\n")
            f.write(f"Base tests: {overall_metrics['total_base_tests']}\n")
            f.write(f"COP tests: {overall_metrics['total_cop_tests']}\n\n")
            f.write(f"Average word count difference: {overall_metrics['avg_word_count_diff_pct']:.2f}%\n")
            f.write(f"Average execution time difference: {overall_metrics['avg_execution_time_diff_pct']:.2f}%\n\n")
            
            f.write("## Key Findings\n\n")
            
            # Word count findings
            if overall_metrics['avg_word_count_diff_pct'] > 20:
                f.write("- COP annotations significantly increase response length, suggesting more detailed explanations\n")
            elif overall_metrics['avg_word_count_diff_pct'] > 0:
                f.write("- COP annotations moderately increase response length\n")
            else:
                f.write("- COP annotations have minimal impact on response length\n")
                
            # Execution time findings
            if overall_metrics['avg_execution_time_diff_pct'] > 20:
                f.write("- COP annotations significantly increase processing time\n")
            elif overall_metrics['avg_execution_time_diff_pct'] > 0:
                f.write("- COP annotations moderately increase processing time\n")
            else:
                f.write("- COP annotations have minimal impact on processing time\n")
