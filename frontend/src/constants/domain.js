export const domain = {
  "id": "gb-0041",
  "direction": "分类建模",
  "title": "桐弦声检故障判读册",
  "slug": "acoustic-bayes",
  "algorithm": "gaussian",
  "entities": "AcousticBatch / AcousticSample / ClassifierRun / InspectionNote",
  "scenario": "合成声学特征→故障类型判读→复检批注；真实训练/验证分离、训练内标准化、类先验展示",
  "visual": "声学频带档案、焦橙",
  "oracle": "对sklearn GaussianNB预测；验证行不参与fit；稀有类不足拒绝",
  "frontend": 18245,
  "backend": 19245,
  "db_port": 17745,
  "database": "MySQL8",
  "batch": 1,
  "code": "TX",
  "source": "声检批次",
  "record": "声学样本",
  "note": "复检批注",
  "source_table": "acoustic_batches",
  "record_table": "acoustic_samples",
  "run_table": "classifier_runs",
  "note_table": "inspection_notes",
  "attribution_table": "bearing_attributions",
  "comparison_table": "comparison_jobs",
  "compare_defaults": {
    "samples": 200000,
    "min_samples": 10000,
    "max_samples": 5000000
  },
  "eyebrow": "TONAL ARCHIVE / 41",
  "headline": "从声学特征，找到复检线索。",
  "subtitle": "桐弦声检组 · 电机试验台的三类故障判读",
  "fields": [
    [
      "rms",
      "均方根振幅",
      "number"
    ],
    [
      "centroid",
      "频谱质心 Hz",
      "number"
    ],
    [
      "kurtosis",
      "峭度",
      "number"
    ],
    [
      "label",
      "复核类型",
      "text"
    ]
  ],
  "params": [
    [
      "folds",
      "分层交叉验证折数",
      3
    ],
    [
      "smoothing",
      "方差平滑系数",
      1e-09
    ]
  ],
  "sample": {
    "rms": 2.1,
    "centroid": 1200,
    "kurtosis": 3.2,
    "label": "正常"
  },
  "seed_count": 240,
  "ink": "oklch(30% .04 48)",
  "accent": "oklch(55% .15 45)",
  "paper": "oklch(94% .025 75)",
  "principle": "分层交叉验证，每折只在训练行拟合均值与方差；后验概率是模型分布，不是检修结论。",
  "default_parameters": {
    "folds": 3,
    "smoothing": 1e-09
  },
  "method_label": "GaussianNB与分层交叉验证、混淆矩阵和后验解释",
  "result_headline": "先看折外预测，再安排复检。",
  "column_labels": {
    "reference": "样本编号",
    "actual": "实际类型",
    "predicted": "预测类型",
    "posterior": "最高类后验",
    "cluster": "分区编号",
    "kind": "微站类型",
    "temperature": "温度 ℃",
    "humidity": "湿度 %",
    "particles": "颗粒浓度",
    "from": "当前章节",
    "to": "下一章节",
    "count": "接续次数",
    "conditional_probability": "条件概率",
    "target_base_rate": "目标章节基率",
    "lift": "提升度",
    "support": "边支持度",
    "actual_minutes": "实测时长 min",
    "predicted_minutes": "预测时长 min",
    "error_minutes": "预测误差 min",
    "visitor": "匿名访客",
    "exhibit": "展品编号",
    "prediction": "预计评分",
    "method": "计算依据",
    "neighbor_count": "参与邻居数"
  }
};
