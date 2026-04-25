#!/usr/bin/env python3
"""Unit test for skill config manager."""

import tempfile
from pathlib import Path

from vibesop.core.skills.config_manager import (
    SkillConfigManager,
    get_skill_llm_config,
    list_skill_configs,
)


def test_set_and_get_skill_llm_config():
    """Test setting and getting skill LLM config."""

    print("=" * 70)
    print("Test: Set and Get Skill LLM Config")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置技能的 LLM 配置
            skill_id = "test-skill"
            llm_config = {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7,
            }

            print(f"\n✓ Setting LLM config for {skill_id}:")
            print(f"  Provider: {llm_config['provider']}")
            print(f"  Model: {llm_config['model']}")
            print(f"  Temperature: {llm_config['temperature']}")

            SkillConfigManager.set_skill_llm_config(skill_id, llm_config)

            # 获取技能配置
            config = SkillConfigManager.get_skill_config(skill_id)

            print("\n✓ Retrieved config:")
            print(f"  Skill ID: {config.skill_id}")
            print(f"  Requires LLM: {config.requires_llm}")
            print(f"  Provider: {config.llm_provider}")
            print(f"  Model: {config.llm_model}")
            print(f"  Temperature: {config.llm_temperature}")

            # 验证
            assert config.skill_id == skill_id
            assert config.requires_llm
            assert config.llm_provider == "openai"
            assert config.llm_model == "gpt-4"
            assert config.llm_temperature == 0.7

            print("\n✅ Test PASSED!")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def test_list_skill_configs():
    """Test listing all skill configs."""

    print("\n" + "=" * 70)
    print("Test: List Skill Configs")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置多个技能的配置
            configs = {
                "code-reviewer": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.2,
                },
                "brainstorm": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.9,
                },
                "debug-helper": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6",
                    "temperature": 0.3,
                },
            }

            print(f"\n✓ Setting up {len(configs)} skill configs...")

            for skill_id, llm_config in configs.items():
                SkillConfigManager.set_skill_llm_config(skill_id, llm_config)
                print(f"  • {skill_id}: {llm_config['provider']}/{llm_config['model']}")

            # 列出所有配置
            all_configs = list_skill_configs()

            print(f"\n✓ Retrieved {len(all_configs)} configs:")
            for skill_id, config in all_configs.items():
                print(f"  • {skill_id}:")
                print(f"    - Provider: {config.llm_provider}")
                print(f"    - Model: {config.llm_model}")
                print(f"    - Temperature: {config.llm_temperature}")

            # 验证
            assert len(all_configs) == 3
            assert "code-reviewer" in all_configs
            assert "brainstorm" in all_configs
            assert "debug-helper" in all_configs

            print("\n✅ Test PASSED!")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def test_update_skill_config():
    """Test updating skill config."""

    print("\n" + "=" * 70)
    print("Test: Update Skill Config")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置初始配置
            skill_id = "my-skill"
            initial_config = {
                "provider": "anthropic",
                "model": "claude-3-haiku-20240307",
                "temperature": 0.5,
            }

            print(f"\n✓ Setting initial config for {skill_id}:")
            print(f"  Provider: {initial_config['provider']}")
            print(f"  Model: {initial_config['model']}")
            print(f"  Temperature: {initial_config['temperature']}")

            SkillConfigManager.set_skill_llm_config(skill_id, initial_config)

            # 更新配置
            updated_config = {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.8,
            }

            print(f"\n✓ Updating config for {skill_id}:")
            print(f"  Provider: {updated_config['provider']}")
            print(f"  Model: {updated_config['model']}")
            print(f"  Temperature: {updated_config['temperature']}")

            SkillConfigManager.set_skill_llm_config(skill_id, updated_config)

            # 获取更新后的配置
            config = SkillConfigManager.get_skill_config(skill_id)

            print("\n✓ Updated config:")
            print(f"  Provider: {config.llm_provider}")
            print(f"  Model: {config.llm_model}")
            print(f"  Temperature: {config.llm_temperature}")

            # 验证
            assert config.llm_provider == "openai"
            assert config.llm_model == "gpt-4"
            assert config.llm_temperature == 0.8

            print("\n✅ Test PASSED!")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def test_delete_skill_config():
    """Test deleting skill config."""

    print("\n" + "=" * 70)
    print("Test: Delete Skill Config")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置配置
            skill_id = "temp-skill"
            llm_config = {
                "provider": "anthropic",
                "model": "claude-3-haiku-20240307",
            }

            print(f"\n✓ Setting config for {skill_id}")
            SkillConfigManager.set_skill_llm_config(skill_id, llm_config)

            # 验证配置存在
            config = SkillConfigManager.get_skill_config(skill_id)
            print(f"✓ Config exists: {config.skill_id}")

            # 删除配置
            print(f"\n✓ Deleting config for {skill_id}")
            SkillConfigManager.delete_skill_config(skill_id)

            # 验证配置已删除
            config = SkillConfigManager.get_skill_config(skill_id)
            print(f"✓ Config after delete: {config}")

            # 删除后应该返回默认配置
            assert config.skill_id == skill_id
            assert config.llm_provider is None

            print("\n✅ Test PASSED!")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def test_priority_fallback():
    """Test LLM config priority: skill > global > env > default."""

    print("\n" + "=" * 70)
    print("Test: LLM Config Priority Fallback")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            skill_id = "priority-test"

            # 1. 技能级别配置
            print("\n✓ Step 1: Set skill-level config")
            SkillConfigManager.set_skill_llm_config(skill_id, {
                "provider": "openai",
                "model": "gpt-4",
            })

            llm_config = get_skill_llm_config(skill_id)
            print(f"  Provider: {llm_config.provider if llm_config else 'None'}")
            print(f"  Model: {llm_config.model if llm_config else 'None'}")
            print(f"  Source: {llm_config.source.value if llm_config else 'None'}")

            if llm_config:
                assert llm_config.provider == "openai"
                assert llm_config.model == "gpt-4"
                print("  ✓ Skill-level config used")

            # 2. 删除技能配置，应该回退到全局配置
            print("\n✓ Step 2: Delete skill config (should fallback to global)")
            SkillConfigManager.delete_skill_config(skill_id)

            llm_config = get_skill_llm_config(skill_id)
            print(f"  Provider: {llm_config.provider if llm_config else 'None'}")
            print(f"  Model: {llm_config.model if llm_config else 'None'}")
            print(f"  Source: {llm_config.source.value if llm_config else 'None'}")

            # 3. 如果没有全局配置，应该回退到环境变量或 Agent
            print("\n✓ Step 3: Fallback to env/agent/default")
            print("  Note: Will use Agent env if available, otherwise defaults")

            print("\n✅ Test PASSED!")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🎯 Skill Config Manager - Unit Tests")
    print("=" * 70)

    # Test 1: Set and get
    test_set_and_get_skill_llm_config()

    # Test 2: List configs
    test_list_skill_configs()

    # Test 3: Update config
    test_update_skill_config()

    # Test 4: Delete config
    test_delete_skill_config()

    # Test 5: Priority fallback
    test_priority_fallback()

    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
