# 服务器与加密协议（DT-30～36，本地实施）

> 状态：已冻结；2026-10-02 起由 [MACHINE-MIGRATION-TASKS.md](../MACHINE-MIGRATION-TASKS.md) 取代。下文验收记录均为历史记录。

维护日期：2026-10-01。真实服务器、域名、账号提供方、容量、备份位置与运维负责人尚未提供；用户本次指定先完成无外部条件部分。本文件的默认方案是实现边界，不是部署记录。

服务使用 Linux、FastAPI、PostgreSQL 17、私有文件存储和 Caddy HTTPS。每账号默认保留 1 GiB 配额，单包最多 256 MiB，分块 4 MiB。已提交历史不自动删除；七天未完成上传可在停止 API 后预览清理。存储空间满、数据库失败与认证失败均不发布未完成包。生产配置不允许测试身份或明文认证降级。

OIDC 提供方须支持 RFC 8628 Device Authorization Grant，例如开启该能力的 Keycloak。客户端是公开客户端，没有内置 client secret。部署方配置 HTTPS issuer、JWKS 和 API audience；服务端只接受 RS256，校验 iss、aud、exp、iat、sub。provider 端关闭不需要的公开注册，并配置 API audience mapper。客户端通过标准用户码在系统浏览器授权；手动检查遵守 interval 和 slow_down，取消／过期清理暂存授权。当前不自动刷新，过期后重新登录。提供方不支持设备授权时明确失败，不替换成密码保存。

用户 ID 来自已验证 issuer/sub 哈希；客户端提交的 user ID 不参与授权。设备另有服务端生成的访问凭据，哈希保存在数据库，客户端凭据与账号 token 一起存在 Windows Credential Manager / macOS Keychain 中。所有空间、上传、分块、版本、下载、回执和撤销检查 owner；设备 ID 本身不能作为访问证明。退出清除 token，保留对应账号密钥；被撤销设备不能继续访问受保护内容。

数据模型见 `server/models.py`；schema v1 启动时显式初始化，未知 schema 停止。新版本 schema 需要后续独立迁移，不能靠 create_all 升级已有库。上传幂等键按用户唯一，重新提交不同内容拒绝。配额在用户行锁定后计入未完成与完成上传。重复同内容分块可重试；重复不同内容拒绝。完成时逐块检查哈希、总长度和总哈希，先发布不可变密文文件，再在数据库事务中创建版本并用 expected_head 条件更新 head。分叉返回 saved=true、conflict=true，双方都保留；没有最后写入覆盖。数据库提交失败留下不可见孤立文件，同一上传重试复用该文件，半包不会出现在列表。

路由由 `server/app.py` 产生 OpenAPI：`/v1/me`，设备登记／列表／撤销，空间创建／列表，上传创建／进度／分块／完成，head／版本列表，版本内容下载，以及最近设备回执。错误使用 401 身份无效、403 设备无授权、404 无所属资源、409 幂等／完整性／未完成冲突、413 体积／配额、422 输入形态、503 存储不可用。跨用户资源统一返回 404。FileResponse 支持 HTTP 范围读取；客户端当前采用有界整包重试，上传支持分块续传。

加密协议 AICLOUD1：`AICLOUD1\n` + canonical JSON header + `\n` + AES-256-GCM ciphertext/tag。header 包含 version=1、alg、key_id、随机 12-byte nonce、明文长度，全部作为 AAD 认证。数据密钥为系统随机 32 bytes；key_id 为 SHA-256 前 32 个十六进制字符，不是密钥。恢复材料 `AIK1-` 后是数据密钥的 canonical base64url；必须保存在密码管理器或独立安全备份，禁止写入配置库、日志、Git、截图或普通文档。账号登录无法替代恢复密钥；所有副本丢失后不能恢复历史明文。

密钥按 server + 已验证 account + space 安全存储。新设备用原恢复材料解锁；已有不同密钥时禁止覆盖。已有云端版本的空间禁止生成替代密钥。加密上传保留本机包，并缓存同次上传密文以获得稳定幂等与续传；下载先核对服务器声明的密文，再 AEAD 解密，最后执行与离线相同的包检查，不直接写 Agent。历史恢复下载旧内容、导入预览、生成新包并上传新的版本，不回退 head。回执只传 space/version/content_id、应用状态和加载核验布尔值，不包含路径或正文；回执失败不回滚已完成的本机应用。

实现依据：[FastAPI 安全依赖](https://fastapi.tiangolo.com/tutorial/security/first-steps/)、[PyJWT issuer/audience 校验](https://pyjwt.readthedocs.io/en/stable/usage.html)、[cryptography AESGCM](https://cryptography.io/en/stable/hazmat/primitives/aead/)、[RFC 8628](https://www.rfc-editor.org/rfc/rfc8628.html)。使用这些标准不代表已通过真实 OIDC、PostgreSQL 并发或服务器验收。
