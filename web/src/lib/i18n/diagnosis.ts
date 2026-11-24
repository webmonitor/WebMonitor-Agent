export const en = {
  "diagnosis.action": "Diagnose and repair with assistant",
  "diagnosis.preparing": "Starting diagnosis…",
  "diagnosis.error": "Unable to start the diagnosis",
  "format.error.run_not_failed": "No failed collection is available to diagnose",
} as const;

export const zh: Record<keyof typeof en, string> = {
  "diagnosis.action": "让助手诊断并修复",
  "diagnosis.preparing": "正在创建诊断…",
  "diagnosis.error": "无法启动诊断",
  "format.error.run_not_failed": "没有可诊断的失败采集",
};
