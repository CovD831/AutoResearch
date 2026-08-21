# 安全、隐私与科研诚信

## 1. 秘密

- LLM_API_KEY 只以 SecretStr 进入进程。
- safe_summary 只返回 configured=true/false。
- .env、.env.local、.env.* 默认 Git ignore；.env.example 例外且无真实值。
- 日志、Evidence metadata、Wiki 和项目 manifest 禁止保存密钥或 Authorization header。

发现已暴露密钥时应按泄露处理并轮换，不得继续复用。

## 2. 外部动作

基础版不实现自动投稿、公开发布、邮件、删除或高成本计算。RELEASED 是内部工作流状态，不等于目标平台成功。

L4 必须：

1. 稿件先通过 L3。
2. LangGraph interrupt 暂停。
3. 具名人工返回 approval。
4. H3 证据写入。
5. Gate 再计算。
6. 审计事件可追溯。

## 3. 论文与版权

- 只读取开放获取或用户有权提供的全文。
- 不绕过登录、付费墙、验证码或访问控制。
- PaperRecord 的存在不代表系统拥有全文许可。
- 项目导出前需检查全文、图表、数据和代码许可证。
- 阅读答案使用供应文本和 locator，材料不足返回 unresolved。

## 4. 科研诚信

系统禁止：

- 伪造论文、作者、DOI、数据、实验、指标或引用。
- 把 planned、estimated、virtual、unknown 写成 performed。
- 把 InnovationCandidate 的 hypothesis 状态写成 confirmed novelty。
- 删除失败实验或与假设冲突的证据以换取 Gate PASS。
- 让 Writer 或 Reviewer 修改 EvidenceItem 后自批。

## 5. 路径和数据隔离

ProjectService 校验目标 resolve 后仍位于 projects_dir，已有项目不覆盖。GraphEdge 禁止跨 partition。Gate 忽略其他 project_id 的证据。

基础版没有认证和多租户 ACL；因此 API 只应本地绑定。生产化需增加认证、授权、速率限制、字段级权限、审计签名和隐私生命周期。

## 6. 已知安全差距

- 没有 WORM/签名审计。
- 没有 SBOM、依赖漏洞扫描或正式 secret scan CI。
- 没有 PostgreSQL RLS、对象存储策略或 Neo4j ACL。
- 没有备份恢复演练。
- 没有 Web UI 防护，因为当前无 Web UI。
