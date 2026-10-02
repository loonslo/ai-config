# Claude Code 配置目录规则

跨工具规则源文件位于仓库的 `common/`。修改公共规则后，从仓库根目录先预览再应用：

```powershell
python scripts/sync.py rules --local device.json
python scripts/sync.py rules --local device.json --apply
```

机器路径和凭据只保存在本地配置中；不要写入同步模板。
