# 外部工具与来源

| 外部工具 | 使用方式 | 来源 |
|---|---|---|
| FFmpeg与ffprobe | 调用用户单独安装的命令行程序处理、探测和解码媒体，不随本项目分发二进制 | [官方文档](https://ffmpeg.org/ffmpeg.html)、[滤镜文档](https://ffmpeg.org/ffmpeg-filters.html)、[许可说明](https://ffmpeg.org/legal.html) |
| Python | 使用用户单独安装的解释器及标准库 | [Python许可](https://docs.python.org/3/license.html) |

本机验证环境的FFmpeg为8.1.2，构建配置包含GPL与libx264。这是实际本机工具状态，不是本项目向用户分发GPL二进制或授予第三方程序权利的声明。

本项目首版不分发剪映程序、原生库、模板或资源，也不实现原作接口桥。来源致敬见[PROVENANCE.md](PROVENANCE.md)。
