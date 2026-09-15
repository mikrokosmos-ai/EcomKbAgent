/**
 * 节点名与进度/画布元数据
 *
 * 键名契约（重要）：
 *   这里的 `IMPORT_STEPS[].key` 与 `QUERY_FLOW_NODES[].step` 必须与后端
 *   `app/utils/task_utils.py::_NODE_NAME_TO_CN` 的中文展示名**逐字一致**——
 *   前端拿到的 done_list / running_list 已经是中文名，名称对不上就会退化成
 *   「其他事件」兜底。新增 LangGraph 节点时需同步本文件。
 */

export interface ImportStep {
  key: string;
  label: string;
  weight: number;
}

/**
 * 导入链路步骤（与 `app/pipelines/import_pipeline/graph.py` 的执行序一致）：
 *   上传 → 检查文件 → PDF转Markdown → Markdown图片处理 → 文档切分
 *        → 主体名称识别 → 向量生成 → 导入向量库 → 导入知识图谱 → 处理完成
 * weight 之和为 100，用于把 done_list 换算成真实进度百分比。
 */
export const IMPORT_STEPS: ImportStep[] = [
  { key: "开始上传文件", label: "开始上传文件", weight: 5 },
  { key: "检查文件", label: "检查文件", weight: 5 },
  { key: "PDF转Markdown", label: "PDF转Markdown", weight: 22 },
  { key: "Markdown图片处理", label: "Markdown图片处理", weight: 25 },
  { key: "文档切分", label: "文档切分", weight: 10 },
  { key: "主体名称识别", label: "主体名称识别", weight: 5 },
  { key: "向量生成", label: "向量生成", weight: 10 },
  { key: "导入向量库", label: "导入向量库", weight: 8 },
  // 知识图谱：导入图末端线性尾插（node_import_milvus → node_import_kg → END）
  { key: "导入知识图谱", label: "导入知识图谱", weight: 8 },
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

/**
 * 查询链路真实拓扑（与 `app/pipelines/query_pipeline/graph.py` 一致）：
 *   确认问题产品 → **四路并行召回**（切片 / 切片(假设性文档) / 网络 / 知识图谱）
 *                → 倒排融合 → 重排序 → 生成答案
 * 四路 x 坐标等距（间距 200）：节点默认宽 156 时左右边界为 52 / 808，均在画布内；
 * 「切片搜索(假设性文档)」名较长，单独加宽到 176，与相邻节点仍不重叠。
 */
export const QUERY_FLOW_NODES: FlowNode[] = [
  { step: "确认问题产品", x: 410, y: 60 },
  { step: "切片搜索", x: 130, y: 170 },
  { step: "切片搜索(假设性文档)", x: 330, y: 170, w: 176 },
  { step: "网络搜索", x: 530, y: 170 },
  { step: "查询知识图谱", x: 730, y: 170 },
  { step: "倒排融合", x: 410, y: 280 },
  { step: "重排序", x: 410, y: 380 },
  { step: "生成答案", x: 410, y: 490 },
];

export const QUERY_FLOW_CONNECTORS: string[] = [
  // 扇出：确认问题产品 → 四路并行召回
  "M410 100 L410 140 L130 140 L130 170",
  "M410 100 L410 140 L330 140 L330 170",
  "M410 100 L410 140 L530 140 L530 170",
  "M410 100 L410 140 L730 140 L730 170",
  // 扇入：四路并行 → 倒排融合
  "M130 210 L130 245 L410 245 L410 280",
  "M330 210 L330 245 L410 245 L410 280",
  "M530 210 L530 245 L410 245 L410 280",
  "M730 210 L730 245 L410 245 L410 280",
  // 主干：倒排融合 → 重排序 → 生成答案
  "M410 320 L410 380",
  "M410 420 L410 490",
];

// 澄清短路支线（虚线）：确认问题产品 → 生成答案，从画布右侧绕行以避开四路节点
export const QUERY_FLOW_SHORT_CIRCUIT = "M488 80 L760 80 L760 490 L488 490";
