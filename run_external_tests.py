from pathlib import Path
import re

# 读取测试文件
test_path = Path(
    "/Users/huchen/Projects/vibesop-py/tests/integration/test_external_skill_execution.py"
)
content = test_path.read_text()

# 修改所有 test_ 方法，添加 -s 输出支持
print("Running external skill integration tests...")
print("=" * 60)
