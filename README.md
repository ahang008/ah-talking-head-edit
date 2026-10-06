# 阿杭独立口播剪辑

从用户自己的视频、带时间的文字和语义决策生成可重新编辑的项目、MP4、SRT及实际验收报告。项目内的ah-talking-head-edit Skill调用本项目独立脚本。

## 首版范围

- Agent决定保留的完整表达与剪口，执行器校验并处理画面、声音和字幕。
- 默认保留输入文件原速，不添加配乐，不修改原片，不覆盖已有输出。
- 项目JSON可编辑后重新验证和渲染。它是本项目格式，尚未验证为剪映原生工程。
- 字幕作为外置SRT交付。若输入画面已有烧录字幕，本版保留这些画面文字；修改外置字幕不会抹去或替换它们。
- 机器验证、人耳听音和原生编辑器兼容性分别记录。首版作为试用版本，不声称优于旧系统。

## 使用入口

读取[ah-talking-head-edit](skills/ah-talking-head-edit/SKILL.md)，按其当前已验证命令执行。Python、FFmpeg、ffprobe需由用户另行合法安装；本项目不分发这些程序。

```bash
python3 skills/ah-talking-head-edit/scripts/clip.py doctor
```

完整项目格式与其他命令见该Skill及其直接引用的项目格式说明。

## 致敬与来源

感谢[yichen-skills](https://github.com/mcncarl/yichen-skills)对将视频制作沉淀成Agent Skill的启发。本项目按阿杭的功能需求独立实现，未将原项目代码、Skill文字、测试、接口桥或模板打包进来。致敬不表示原作者参与、认可或授权。

实际来源与隔离过程见[PROVENANCE.md](PROVENANCE.md)，外部工具见[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。来源记录不构成法律上的原创性保证。

## 许可

沿用阿杭现有项目的[AH Source Available Non-Commercial License 1.0](LICENSE)。这是源码可见非商业许可，不标作OSI开源；第三方工具继续适用其各自许可。

## 本地证据

设计、实现计划和验收说明位于本项目编号Markdown文件。机器检查、真实素材运行、旧文件摘要基线位于evidence目录；该目录不进入公开代码版本。
