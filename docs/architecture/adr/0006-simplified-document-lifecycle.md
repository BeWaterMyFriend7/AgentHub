---
status: accepted
date: 2026-07-18
---

# 按产品、工程、质量和过程收敛文档目录

项目既需要区分 PRD、技术设计、ADR、BDD 和测试证据，也需要避免为当前规模创建过多顶层目录和空子目录。因此保留 `prd/`，将当前架构、单一技术设计和 ADR 收敛到 `architecture/`，将 BDD、测试策略和验证记录收敛到 `quality/`，将路线图、待办和单一经验文档收敛到 `process/`；BDD Feature 直接放在 `quality/bdd/`，待内容规模实际增长后再拆分。
