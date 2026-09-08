/**
 * 节点名与进度/画布元数据
 * 导入 9 步权重用于真实进度；查询 7 节点坐标用于 PipelineFlow 链路图。
 */

export interface ImportStep {
  key: string;
  label: string;
  weight: number;
}

export const IMPORT_STEPS: ImportStep[] = [
  { key: "开始上传文件", label: "开始上传文件", weight: 5 },
  { key: "检查文件", label: "检查文件", weight: 5 },
  { key: "PDF转Markdown", label: "PDF转Markdown", weight: 25 },
  { key: "Markdown图片处理", label: "Markdown图片处理", weight: 30 },
  { key: "文档切分", label: "文档切分", weight: 10 },
  { key: "主体名称识别", label: "主体名称识别", weight: 5 },
  { key: "向量生成", label: "向量生成", weight: 10 },
  { key: "导入向量库", label: "导入向量库", weight: 8 },
  { key: "处理完成", label: "处理完成", weight: 2 },
];

export function importProgress(doneList: string[]): number {
  const done = new Set(doneList);
  let total = 0;
  let acc = 0;
  for (const step of IMPORT_STEPS) {
    total += step.weight;
    if (done.has(step.key)) acc += step.weight;
  }
  return total > 0 ? Math.round((acc / total) * 100) : 0;
}

export interface FlowNode {
  step: string;
  x: number;
  y: number;
  w?: number;
}

// 画布逻辑尺寸
export const QUERY_CANVAS_W = 820;
export const QUERY_CANVAS_H = 540;

export const QUERY_FLOW_NODES: FlowNode[] = [
  { step: "确认问题产品", x: 410, y: 60 },
  { step: "切片搜索", x: 150, y: 170 },
  { step: "切片搜索(假设性文档)", x: 410, y: 170, w: 176 },
  { step: "网络搜索", x: 670, y: 170 },
  { step: "倒排融合", x: 410, y: 280 },
  { step: "重排序", x: 410, y: 380 },
  { step: "生成答案", x: 410, y: 490 },
];

export const QUERY_FLOW_CONNECTORS: string[] = [
  "M410 100 L410 135 L150 135 L150 170",
  "M410 100 L410 170",
  "M410 100 L410 135 L670 135 L670 170",
  "M150 210 L150 245 L410 245 L410 280",
  "M410 210 L410 280",
  "M670 210 L670 245 L410 245 L410 280",
  "M410 320 L410 380",
  "M410 420 L410 490",
];

// 澄清短路支线（虚线）
export const QUERY_FLOW_SHORT_CIRCUIT = "M488 80 L670 80 L670 490 L488 490";
