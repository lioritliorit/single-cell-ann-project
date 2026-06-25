"""
测试报告生成器
用于生成Markdown格式的测试报告
"""

import os
import time
from datetime import datetime


class TestReporter:
    """测试报告生成器"""
    
    def __init__(self, report_dir=None):
        if report_dir is None:
            report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        self.report_dir = report_dir
        self.results = {}
        self.start_time = None
        self.end_time = None
        
        if not os.path.exists(self.report_dir):
            os.makedirs(self.report_dir)
    
    def start_test(self):
        """开始测试"""
        self.start_time = time.time()
        self.results = {}
        print("="*70)
        print("测试报告生成器已启动")
        print("="*70)
    
    def add_result(self, test_name, success, details=None):
        """添加测试结果"""
        self.results[test_name] = {
            "success": success,
            "details": details or "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name}: {status}")
    
    def end_test(self):
        """结束测试"""
        self.end_time = time.time()
    
    def generate_markdown_report(self):
        """生成Markdown测试报告"""
        filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = os.path.join(self.report_dir, filename)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["success"])
        failed_tests = total_tests - passed_tests
        duration = self.end_time - self.start_time if (self.end_time and self.start_time) else 0
        
        md_content = f"""# 单细胞 ANN 系统测试报告

**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**测试时长**: {duration:.2f} 秒

## 测试摘要

| 指标 | 数值 |
|------|------|
| 总测试数 | {total_tests} |
| 通过 | {passed_tests} |
| 失败 | {failed_tests} |
| 通过率 | {passed_tests/total_tests*100:.1f}% |

## 测试详情

"""
        
        for test_name, result in self.results.items():
            status_emoji = "✅" if result["success"] else "❌"
            status_text = "通过" if result["success"] else "失败"
            
            md_content += f"### {status_emoji} {test_name}\n\n"
            md_content += f"- **状态**: {status_text}\n"
            md_content += f"- **时间**: {result['timestamp']}\n"
            
            if result["details"]:
                md_content += f"- **详情**: {result['details']}\n"
            
            md_content += "\n"
        
        md_content += f"""---
*本报告由系统自动生成*
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        print("="*70)
        print(f"测试报告已生成: {filepath}")
        print("="*70)
        
        # 同时生成一个 latest.md 作为最新报告
        latest_path = os.path.join(self.report_dir, "latest_test_report.md")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        return filepath


# 全局报告器实例
_reporter = None


def get_reporter():
    """获取全局报告器实例"""
    global _reporter
    if _reporter is None:
        _reporter = TestReporter()
    return _reporter
