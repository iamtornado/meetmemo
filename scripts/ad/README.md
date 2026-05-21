# AD 迁移：mywind 人工智能技术中心 → dltornado2\myse\IT

## 推荐：Python（Linux / macOS / Windows 均可）

无需 RSAT，在本机或 MeetMemo 服务器上执行：

```bash
cd /path/to/MeetMemo/scripts/ad

# 推荐：uv 独立虚拟环境（不污染系统 Python / backend 环境）
uv venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -r requirements-ad-sync.txt
# 或: uv pip install .

# 或不用 venv：pip install -r requirements-ad-sync.txt

export SOURCE_LDAP_HOST=dc01.mywind.com.cn    # 生产域控 FQDN
export SOURCE_LDAP_USER='MYWIND\\syncuser'
export SOURCE_LDAP_PASSWORD='***'
export TARGET_LDAP_HOST=dc01.dltornado2.com  # 测试域控 FQDN
export TARGET_LDAP_USER='DLTORNADO2\\admin'
export TARGET_LDAP_PASSWORD='***'

# 预检
python sync_ai_tech_center.py --what-if

# 正式同步（设置测试用户密码需 LDAPS）
python sync_ai_tech_center.py \
  --sam-suffix _test \
  --default-password 'ChangeMe!2026' \
  --set-password
```

| 参数 | 说明 |
|------|------|
| `--what-if` | 只读生产 + 预览测试，不写入 |
| `--source-host` / `--target-host` | 域控主机名（建议 FQDN，不要只用域名） |
| `--sam-suffix` | 测试账号后缀，如 `_test` |
| `--set-password` | 通过 LDAPS:636 设置初始密码 |
| `--skip-groups` | 不同步组 |
| `--save-json ./backup` | 导出 JSON 备份 |

凭据也可用环境变量（见脚本 `--help`）。

**MeetMemo 后端容器里**已含 `ldap3`，也可在 `backend` 目录用现有 venv 直接跑脚本，不必再建环境；在**本机/跳板机**单独跑 AD 同步时，更建议 `scripts/ad` 下用 uv。

```bash
# 不 activate 时也可：
cd scripts/ad && uv run python sync_ai_tech_center.py --what-if
```

---


## PowerShell（需 Windows + RSAT）

## 一条脚本完成

```powershell
cd <MeetMemo>\scripts\ad

# 1) 预检（只读生产 + 预览测试域变更，不写入）
.\Sync-AITechCenter-To-Dltornado2.ps1 -WhatIf

# 2) 正式同步（依次提示输入生产域、测试域管理员密码）
.\Sync-AITechCenter-To-Dltornado2.ps1 `
  -DefaultPassword 'ChangeMe!2026' `
  -SamAccountSuffix '_test' `
  -SaveCsv C:\ad-migration\backup
```

无需分 Export / Import 两步；数据在内存中从生产域读到测试域。

## 路径

| | DN |
|--|-----|
| 生产读取根 | `OU=人工智能技术中心,OU=中央研究院,OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn` |
| 测试挂载 | `OU=IT,OU=myse,DC=dltornado2,DC=com` |
| 测试结构 | `IT\中央研究院\人工智能技术中心\`（含 `人工智能产品交付室` 等子 OU） |

## 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `-SourceServer` | mywind.com.cn | 生产域控 |
| `-TargetServer` | dltornado2.com | 测试域控 |
| `-SourceCredential` | 交互输入 | 生产域凭据 |
| `-TargetCredential` | 交互输入 | 测试域凭据 |
| `-SamAccountSuffix` | 空 | 如 `_test` 避免账号重名 |
| `-DefaultPassword` | ChangeMe!2026 | 新用户初始密码 |
| `-SkipGroups` | - | 不同步组 |
| `-WhatIf` | - | 仅预览 |
| `-SaveCsv` | 空 | 可选备份 CSV 目录 |

## 批量：中央研究院 OU 下用户（取消下次改密 + 密码永不过期）

对测试域 `OU=中央研究院,OU=IT,OU=myse,DC=dltornado2,DC=com` 及其子 OU 下**所有用户**：

- `pwdLastSet = -1`（取消「下次登录必须改密」）
- `userAccountControl` 增加「密码永不过期」标志

需 **测试域管理员** + **LDAPS 636**：

```bash
cd scripts/ad
export TARGET_LDAP_HOST=dc01.dltornado2.com
export TARGET_LDAP_USER='DLTORNADO2\admin'
export TARGET_LDAP_PASSWORD='***'

# 预检
python batch_fix_central_research_users.py --what-if

# 正式执行（不改密码，只改标志）
python batch_fix_central_research_users.py

# 同时把密码重置为默认（可选）
python batch_fix_central_research_users.py --set-password --default-password 'ChangeMe!2026'
```

| 参数 | 说明 |
|------|------|
| `--base-dn` | 搜索根 OU，默认中央研究院 |
| `--what-if` | 只列出将修改的账号 |
| `--set-password` | 顺带重置为 `--default-password` |

单账号仍可用 `reset_test_user_password.py --sam A01309`。

---

## MeetMemo 登录失败（默认密码正确仍报 Invalid credentials）

同步时若设置了「下次登录须改密」（Python 旧版 `pwdLastSet=0` 或 PS `-ChangePasswordAtLogon $true`），LDAP 绑定会返回 **773**，MeetMemo 无法完成改密流程。

**域管在测试域控上修复单个账号（示例 A01309）：**

```powershell
Set-ADAccountPassword -Identity A01309 -Reset -NewPassword (ConvertTo-SecureString 'ChangeMe!2026' -AsPlainText -Force)
Set-ADUser -Identity A01309 -ChangePasswordAtLogon $false
```

修复后使用 `A01309` 或 `A01309@dltornado2.com` + `ChangeMe!2026` 登录 MeetMemo。

临时可用本地管理员：`admin@example.com` / `admin123`（若已初始化）。

---

## 前置

- Windows + RSAT **ActiveDirectory** 模块
- 生产账号：对源 OU **读**
- 测试账号：对 `myse\IT` **建 OU/用户/组**

## MeetMemo LDAP（测试）

```env
LDAP_BASE_DN=OU=人工智能技术中心,OU=中央研究院,OU=IT,OU=myse,DC=dltornado2,DC=com
LDAP_DOMAIN=dltornado2.com
```

登录用 **sAMAccountName**（不是中文显示名）。
