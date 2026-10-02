# 第三方依赖与发布检查

维护日期：2026-10-01。依赖实际清单由 Python requirements、desktop/package-lock.json 与 Cargo.lock 决定。正式发布时应把安装环境的完整 LICENSE/NOTICE 和传递依赖清单随安装包分发；本文件是索引，不代替版权文本。

| 主要依赖 | 许可证 | 来源 |
| --- | --- | --- |
| Python | PSF | https://docs.python.org/3/license.html |
| Tauri / plugins | MIT / Apache-2.0 | https://github.com/tauri-apps/tauri |
| React / TypeScript / Vite | MIT | npm 包内 LICENSE 与 package.json |
| tomlkit | MIT | 安装包 LICENSE |
| PyInstaller | GPL-2.0 with bootloader exception | https://pyinstaller.org/en/stable/license.html |
| cryptography | Apache-2.0 / BSD-3-Clause | 安装包 LICENSE，另包含 OpenSSL 等 notices |
| keyring | MIT | 安装包 LICENSE |
| HTTPX / FastAPI / SQLAlchemy / PyJWT | BSD-3-Clause / MIT | 各安装包 LICENSE |
| PostgreSQL | PostgreSQL License | 官方容器与源码 LICENSE |
| Caddy | Apache-2.0 | 官方容器与源码 LICENSE |

本轮 Windows 开发预览归档：`scripts/collect-release-notices.py --fetch-missing --output release-artifacts/notices-0.2.0-complete` 收集 **322 项、缺少版权文本 0 项**；包含 Python 3.14 运行时、Windows Python 构建／运行依赖、实际安装的 npm 依赖和 Windows Cargo 依赖图。未在本机安装的 53 个可选平台 npm 包在索引中单独排除；三个本机 npm native binding 的版权文本注明来自同版本所属主包；缺文本 Cargo 项优先按发布包 `.cargo_vcs_info.json` 的精确 commit 获取上游，MPL 2.0 从 Mozilla 官方页面保存全文。来源 URL 和 commit 在归档 index.json 里记录。

伴随归档位于 `release-artifacts/AI-Config-0.2.0-Windows-NOTICES-full.zip`，发布清单记录其 SHA-256。此归档应与预览安装包一起分发，尚未嵌入安装器。复现需要依赖已经安装、cargo 可用和上游访问；不包含未构建 Mac 平台、服务端镜像操作系统及其完整依赖版权审核，不是完整 SBOM 或正式发布合规结论。

当前仍是未签名预览版本；干净账户安装、macOS 签名／公证、跨平台／服务端完整许可证审核、镜像 digest 与真实部署结果尚未验收。
