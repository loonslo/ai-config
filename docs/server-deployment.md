# 部署与恢复（DT-38，未部署）

> 状态：已冻结；2026-10-02 起由 [MACHINE-MIGRATION-TASKS.md](../MACHINE-MIGRATION-TASKS.md) 取代。下文验收记录均为历史记录。

维护日期：2026-10-01。这里只交付可审查部署文件；没有执行远程部署、覆盖、DNS 修改或真实恢复演练。

准备 Linux + Docker Compose、指向服务器的域名、443/80 入站、私有存储目录、OIDC 提供方和独立备份位置。`deploy/environment.example` 只说明变量名，真实数据库密码和连接字符串放本机环境或 secret manager，禁止放仓库。包目录须由容器 UID 10001 读写，只对容器挂载；PostgreSQL 不暴露端口。首版由用户指定运维负责人维护 TLS、备份、配额和身份提供方。请先核对 OIDC 设备授权与 audience mapper。

部署命令（仅在目标确认后执行）：

```text
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml build api
docker compose -f deploy/compose.yaml up -d
```

不要将带展开密钥的 `compose config` 结果保存或贴到聊天。Dockerfile 只复制 server/ 白名单，不包含工作区、客户端数据、登录文件或测试。首次启动初始化 schema v1；迁移更高版本前必须备份并提供专用迁移脚本。依赖版本锁定在 `server/requirements.txt`；基础镜像 tag 固定但还没有记录真实构建 digest，不能称为位级可重复镜像。

HTTPS `/health` 核对数据库与存储可用性。正常业务错误不会把 token 或正文打印到日志；uvicorn access log 默认关闭。健康检查不能代替磁盘剩余容量监控；运维应设置磁盘容量告警，并定期验证备份可恢复。

一致备份先停止 API，数据库保持运行。`maintenance.py` 通过二进制管道执行 pg_dump -Fc；复制包存储前后核对完整哈希，输出新目录与 backup.json，已有目标拒绝覆盖。Linux 维护环境需 Docker Compose 与 Python；清理另需安装 server requirements。从仓库根执行：

```text
docker compose -f deploy/compose.yaml stop api
python -m deploy.maintenance backup --path /absolute/new-backup-directory
docker compose -f deploy/compose.yaml start api
```

备份必须另行放到独立安全目的地。脚本成功仅表示数据库 dump 已生成、包字节一致，不表示恢复验收。实际备份包含密文包和账号索引，应按私有资料保管；不含客户端解密密钥，恢复材料需要独立备份。

恢复仅允许独立空环境：空 PostgreSQL、空包目录、API 已停止。先预览精确目标，再在同一目标加 --confirm。不清空已有数据库，不覆盖已有包。恢复失败保持 API 停止，保留原备份和现场。完成后还需真实客户端列版本、下载、解密、导入与加载核验。

```text
python -m deploy.maintenance restore --path /absolute/verified-backup
python -m deploy.maintenance restore --path /absolute/verified-backup --confirm
```

清理只处理过期未完成上传；默认预览，--confirm 才删除。已提交版本与历史不在清理范围：

```text
python -m deploy.maintenance cleanup
python -m deploy.maintenance cleanup --confirm
```

尚未验证：真实服务器、PostgreSQL 多连接并发、容器与 TLS 启动、真实 OIDC、独立备份目的地、恢复演练和客户端双机操作。需要外部环境才能完成 DT-37／38 的实机要求。
