#!/usr/bin/env python3
"""Generate visual CI reports from test results and coverage data."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

import matplotlib.pyplot as plt
import pandas as pd
from jinja2 import Template


class CIReportGenerator:
    """Generate comprehensive CI reports with visualizations."""
    
    def __init__(self, artifacts_dir: Path, output_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize data containers
        self.test_results = {}
        self.coverage_data = {}
        self.security_reports = {}
        self.benchmark_data = {}
        
    def load_artifacts(self):
        """Load all CI artifacts."""
        # Load test results
        for result_file in self.artifacts_dir.glob("**/test-results-*.xml"):
            python_version = result_file.stem.split("-")[-1]
            self.test_results[python_version] = self._parse_junit_xml(result_file)
        
        # Load coverage reports
        for coverage_file in self.artifacts_dir.glob("**/coverage.xml"):
            self.coverage_data = self._parse_coverage_xml(coverage_file)
            break  # Use first coverage file found
        
        # Load security reports
        for report_name in ["bandit-report", "safety-report", "pip-audit-report"]:
            report_file = self.artifacts_dir / report_name / f"{report_name}.json"
            if report_file.exists():
                try:
                    with open(report_file) as f:
                        content = f.read()
                        if content.strip():  # Check if file is not empty
                            self.security_reports[report_name] = json.loads(content)
                        else:
                            print(f"Warning: {report_name} is empty")
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse {report_name}: {e}")
        
        # Load benchmark data
        for benchmark_file in self.artifacts_dir.glob("**/benchmark-results-*.json"):
            python_version = benchmark_file.stem.split("-")[-1]
            try:
                with open(benchmark_file) as f:
                    content = f.read()
                    if content.strip():
                        self.benchmark_data[python_version] = json.loads(content)
                    else:
                        print(f"Warning: Benchmark file for Python {python_version} is empty")
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse benchmark for Python {python_version}: {e}")
    
    def _parse_junit_xml(self, xml_file: Path) -> Dict[str, Any]:
        """Parse JUnit XML test results."""
        # Simplified parsing - in production use xml.etree or lxml
        import xml.etree.ElementTree as ET
        
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        results = {
            "total": int(root.get("tests", 0)),
            "passed": 0,
            "failed": int(root.get("failures", 0)),
            "errors": int(root.get("errors", 0)),
            "skipped": int(root.get("skipped", 0)),
            "time": float(root.get("time", 0)),
            "test_cases": []
        }
        
        results["passed"] = results["total"] - results["failed"] - results["errors"] - results["skipped"]
        
        for testcase in root.findall(".//testcase"):
            case_data = {
                "name": testcase.get("name"),
                "classname": testcase.get("classname"),
                "time": float(testcase.get("time", 0)),
                "status": "passed"
            }
            
            if testcase.find("failure") is not None:
                case_data["status"] = "failed"
            elif testcase.find("error") is not None:
                case_data["status"] = "error"
            elif testcase.find("skipped") is not None:
                case_data["status"] = "skipped"
            
            results["test_cases"].append(case_data)
        
        return results
    
    def _parse_coverage_xml(self, xml_file: Path) -> Dict[str, Any]:
        """Parse coverage XML report."""
        import xml.etree.ElementTree as ET
        
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        coverage = {
            "line_rate": float(root.get("line-rate", 0)) * 100,
            "branch_rate": float(root.get("branch-rate", 0)) * 100,
            "total_lines": 0,
            "covered_lines": 0,
            "packages": []
        }
        
        for package in root.findall(".//package"):
            pkg_data = {
                "name": package.get("name"),
                "line_rate": float(package.get("line-rate", 0)) * 100,
                "branch_rate": float(package.get("branch-rate", 0)) * 100,
            }
            coverage["packages"].append(pkg_data)
        
        return coverage
    
    def generate_visualizations(self):
        """Generate visualization charts."""
        # Test results pie chart
        self._generate_test_results_chart()
        
        # Coverage bar chart
        self._generate_coverage_chart()
        
        # Performance benchmarks
        self._generate_benchmark_chart()
        
        # Security issues summary
        self._generate_security_chart()
    
    def _generate_test_results_chart(self):
        """Generate test results pie chart."""
        if not self.test_results:
            return
        
        fig, axes = plt.subplots(1, len(self.test_results), figsize=(6*len(self.test_results), 6))
        if len(self.test_results) == 1:
            axes = [axes]
        
        for idx, (version, results) in enumerate(self.test_results.items()):
            ax = axes[idx]
            
            sizes = [results["passed"], results["failed"], results["errors"], results["skipped"]]
            labels = ["Passed", "Failed", "Errors", "Skipped"]
            colors = ["#28a745", "#dc3545", "#ffc107", "#6c757d"]
            
            # Filter out zero values
            filtered = [(size, label, color) for size, label, color in zip(sizes, labels, colors) if size > 0]
            if filtered:
                sizes, labels, colors = zip(*filtered)
                
                ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
                ax.set_title(f"Test Results - Python {version}")
        
        plt.tight_layout()
        plt.savefig(self.output_dir / "test_results.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _generate_coverage_chart(self):
        """Generate coverage bar chart."""
        if not self.coverage_data or not self.coverage_data.get("packages"):
            return
        
        packages = self.coverage_data["packages"]
        names = [pkg["name"] for pkg in packages]
        line_rates = [pkg["line_rate"] for pkg in packages]
        branch_rates = [pkg["branch_rate"] for pkg in packages]
        
        x = range(len(names))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.bar([i - width/2 for i in x], line_rates, width, label='Line Coverage', color='#28a745')
        ax.bar([i + width/2 for i in x], branch_rates, width, label='Branch Coverage', color='#17a2b8')
        
        ax.set_xlabel('Package')
        ax.set_ylabel('Coverage %')
        ax.set_title('Code Coverage by Package')
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=45, ha='right')
        ax.legend()
        ax.axhline(y=90, color='r', linestyle='--', label='Target (90%)')
        ax.set_ylim(0, 105)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / "coverage.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _generate_benchmark_chart(self):
        """Generate performance benchmark chart."""
        if not self.benchmark_data:
            return
        
        # Extract benchmark data
        all_benchmarks = {}
        for version, data in self.benchmark_data.items():
            for benchmark in data.get("benchmarks", []):
                name = benchmark["name"]
                if name not in all_benchmarks:
                    all_benchmarks[name] = {}
                all_benchmarks[name][version] = benchmark["stats"]["mean"]
        
        if not all_benchmarks:
            return
        
        # Create comparison chart
        fig, ax = plt.subplots(figsize=(10, 6))
        
        benchmark_names = list(all_benchmarks.keys())
        versions = list(next(iter(all_benchmarks.values())).keys())
        
        x = range(len(benchmark_names))
        width = 0.35
        
        for idx, version in enumerate(versions):
            values = [all_benchmarks[name].get(version, 0) for name in benchmark_names]
            ax.bar([i + idx * width for i in x], values, width, label=f'Python {version}')
        
        ax.set_xlabel('Benchmark')
        ax.set_ylabel('Time (seconds)')
        ax.set_title('Performance Benchmarks')
        ax.set_xticks([i + width/2 for i in x])
        ax.set_xticklabels(benchmark_names, rotation=45, ha='right')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(self.output_dir / "benchmarks.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _generate_security_chart(self):
        """Generate security issues summary chart."""
        if not self.security_reports:
            return
        
        # Count issues by severity
        severities = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        
        # Parse different report formats
        for report_name, report_data in self.security_reports.items():
            if report_name == "bandit-report" and "results" in report_data:
                for issue in report_data["results"]:
                    severity = issue.get("issue_severity", "").upper()
                    if severity in severities:
                        severities[severity] += 1
            
            elif report_name == "safety-report" and isinstance(report_data, list):
                for vuln in report_data:
                    severity = "HIGH"  # Safety doesn't provide severity levels
                    severities[severity] += 1
            
            elif report_name == "pip-audit-report" and "vulnerabilities" in report_data:
                for vuln in report_data["vulnerabilities"]:
                    severity = "HIGH"  # pip-audit doesn't provide severity levels
                    severities[severity] += 1
        
        # Create bar chart
        fig, ax = plt.subplots(figsize=(8, 6))
        
        severity_levels = list(severities.keys())
        counts = list(severities.values())
        colors = ["#dc3545", "#fd7e14", "#ffc107", "#28a745"]
        
        bars = ax.bar(severity_levels, counts, color=colors)
        
        ax.set_xlabel('Severity')
        ax.set_ylabel('Number of Issues')
        ax.set_title('Security Issues by Severity')
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(height)}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / "security.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def generate_html_report(self):
        """Generate HTML summary report."""
        template = Template("""
<!DOCTYPE html>
<html>
<head>
    <title>CI Report - {{ timestamp }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1, h2 { color: #333; }
        .summary { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .metric { display: inline-block; margin: 10px 20px; }
        .metric-value { font-size: 2em; font-weight: bold; }
        .passed { color: #28a745; }
        .failed { color: #dc3545; }
        .warning { color: #ffc107; }
        img { max-width: 100%; height: auto; margin: 20px 0; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h1>PenEllE CI Report</h1>
    <p>Generated: {{ timestamp }}</p>
    
    <div class="summary">
        <h2>Test Summary</h2>
        {% for version, results in test_results.items() %}
        <div class="metric">
            <div>Python {{ version }}</div>
            <div class="metric-value {% if results.failed == 0 %}passed{% else %}failed{% endif %}">
                {{ results.passed }}/{{ results.total }}
            </div>
            <div>{{ "%.2f"|format(results.time) }}s</div>
        </div>
        {% endfor %}
    </div>
    
    <div class="summary">
        <h2>Coverage Summary</h2>
        <div class="metric">
            <div>Line Coverage</div>
            <div class="metric-value {% if coverage_data.line_rate >= 90 %}passed{% else %}failed{% endif %}">
                {{ "%.1f"|format(coverage_data.line_rate) }}%
            </div>
        </div>
        <div class="metric">
            <div>Branch Coverage</div>
            <div class="metric-value {% if coverage_data.branch_rate >= 85 %}passed{% else %}warning{% endif %}">
                {{ "%.1f"|format(coverage_data.branch_rate) }}%
            </div>
        </div>
    </div>
    
    <h2>Test Results</h2>
    <img src="test_results.png" alt="Test Results">
    
    <h2>Code Coverage</h2>
    <img src="coverage.png" alt="Code Coverage">
    
    {% if benchmark_data %}
    <h2>Performance Benchmarks</h2>
    <img src="benchmarks.png" alt="Performance Benchmarks">
    {% endif %}
    
    {% if security_reports %}
    <h2>Security Analysis</h2>
    <img src="security.png" alt="Security Issues">
    {% endif %}
    
    <h2>Detailed Test Results</h2>
    {% for version, results in test_results.items() %}
    <h3>Python {{ version }}</h3>
    <table>
        <tr>
            <th>Test Case</th>
            <th>Status</th>
            <th>Time (s)</th>
        </tr>
        {% for test in results.test_cases[:10] %}
        <tr>
            <td>{{ test.name }}</td>
            <td class="{% if test.status == 'passed' %}passed{% else %}failed{% endif %}">
                {{ test.status }}
            </td>
            <td>{{ "%.3f"|format(test.time) }}</td>
        </tr>
        {% endfor %}
        {% if results.test_cases|length > 10 %}
        <tr>
            <td colspan="3">... and {{ results.test_cases|length - 10 }} more tests</td>
        </tr>
        {% endif %}
    </table>
    {% endfor %}
</body>
</html>
        """)
        
        html_content = template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            test_results=self.test_results,
            coverage_data=self.coverage_data or {"line_rate": 0, "branch_rate": 0},
            benchmark_data=self.benchmark_data,
            security_reports=self.security_reports
        )
        
        with open(self.output_dir / "index.html", "w") as f:
            f.write(html_content)
    
    def generate_markdown_summary(self):
        """Generate markdown summary for PR comments."""
        template = Template("""## CI Report Summary

**Generated:** {{ timestamp }}

### 🧪 Test Results
{% if test_results %}
{% for version, results in test_results.items() %}
- **Python {{ version }}**: {{ results.passed }}/{{ results.total }} passed ({{ "%.1f"|format((results.passed / results.total * 100) if results.total > 0 else 0) }}%) in {{ "%.2f"|format(results.time) }}s
  {% if results.failed > 0 %}⚠️ {{ results.failed }} failed{% endif %}
  {% if results.errors > 0 %}❌ {{ results.errors }} errors{% endif %}
{% endfor %}
{% else %}
- No test results found
{% endif %}

### 📊 Coverage
- **Line Coverage**: {{ "%.1f"|format(coverage_data.line_rate) }}% {% if coverage_data.line_rate >= 90 %}✅{% else %}❌{% endif %}
- **Branch Coverage**: {{ "%.1f"|format(coverage_data.branch_rate) }}%

### 🔒 Security
{% if security_issues.total > 0 %}
- **Critical**: {{ security_issues.CRITICAL }} {% if security_issues.CRITICAL > 0 %}🚨{% endif %}
- **High**: {{ security_issues.HIGH }} {% if security_issues.HIGH > 0 %}⚠️{% endif %}
- **Medium**: {{ security_issues.MEDIUM }}
- **Low**: {{ security_issues.LOW }}
{% else %}
✅ No security issues found
{% endif %}

### 📈 Performance
{% if benchmark_summary %}
Average execution times:
{% for name, time in benchmark_summary.items() %}
- {{ name }}: {{ "%.3f"|format(time) }}s
{% endfor %}
{% endif %}

---
[View Full Report](../ci-reports/index.html)
        """)
        
        # Calculate security issues
        security_issues = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "total": 0}
        for report_name, report_data in self.security_reports.items():
            if report_name == "bandit-report" and "results" in report_data:
                for issue in report_data["results"]:
                    severity = issue.get("issue_severity", "").upper()
                    if severity in security_issues:
                        security_issues[severity] += 1
                        security_issues["total"] += 1
        
        # Calculate benchmark summary
        benchmark_summary = {}
        if self.benchmark_data:
            for version, data in self.benchmark_data.items():
                for benchmark in data.get("benchmarks", []):
                    name = benchmark["name"]
                    if name not in benchmark_summary:
                        benchmark_summary[name] = []
                    benchmark_summary[name].append(benchmark["stats"]["mean"])
        
        # Average the benchmarks
        for name in benchmark_summary:
            if benchmark_summary[name]:
                benchmark_summary[name] = sum(benchmark_summary[name]) / len(benchmark_summary[name])
            else:
                benchmark_summary[name] = 0
        
        markdown_content = template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            test_results=self.test_results,
            coverage_data=self.coverage_data or {"line_rate": 0, "branch_rate": 0},
            security_issues=security_issues,
            benchmark_summary=benchmark_summary
        )
        
        with open(self.output_dir / "summary.md", "w") as f:
            f.write(markdown_content)
    
    def generate_reports(self):
        """Generate all reports."""
        print("Loading CI artifacts...")
        self.load_artifacts()
        
        print("Generating visualizations...")
        self.generate_visualizations()
        
        print("Generating HTML report...")
        self.generate_html_report()
        
        print("Generating markdown summary...")
        self.generate_markdown_summary()
        
        print(f"Reports generated in {self.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Generate CI reports")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        required=True,
        help="Directory containing CI artifacts"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ci-reports"),
        help="Output directory for reports"
    )
    
    args = parser.parse_args()
    
    if not args.artifacts_dir.exists():
        print(f"Error: Artifacts directory {args.artifacts_dir} does not exist")
        sys.exit(1)
    
    generator = CIReportGenerator(args.artifacts_dir, args.output_dir)
    generator.generate_reports()


if __name__ == "__main__":
    main()