# 이전 내역

원본: `iot-hackathon-brainstorm/evaluation/` → 현재 레포 `docs/qwen_evaluation/`.

원본 삭제·Git commit/push·서버 설정 변경은 하지 않았다. 조사 수상작과 브레인스토밍 문서는 포함하지 않는다. 기존 `qc-executorch-guide/`와 루트 README는 변경하지 않았다.

기존 보고서는 본문을 보존하고 로컬 `.py`/`.json` 링크만 Markdown 아카이브 경로로 바꿨다. Python/JSON은 코드 블록으로 보존했다. 이후 인계 문서는 폐기하고 제품·보드 관련 정보는 [아키텍처](../ARCHITECTURE.md), 평가 환경·결과·실행 지침은 [평가 인덱스](README.md)에 통합했다. 원본 바이트 SHA-256은 검증 기록용이고 줄바꿈 정규화 후의 hash와 구분한다.

| 원본 | 이전 파일 | 원본 SHA-256 |
|---|---|---|
| `evaluation/analyze_qwen.py` | [analyze_qwen.py.md](analyze_qwen.py.md) | `a3d75e6e7e1cbf522df3bec027a1ea1d7302efee72edb0323227e4fd1a350024` |
| `evaluation/analyze_stt.py` | [analyze_stt.py.md](analyze_stt.py.md) | `93e10272af8a5242af69a66a4e3d94a53abe45a9cdc9cd436ecb9510ac8cd0f0` |
| `evaluation/english_cases.py` | [english_cases.py.md](english_cases.py.md) | `efd943846fc558b4a58d34df51a25da047af8508f4f6838f0a1c35f104567151` |
| `evaluation/qwen_analysis.json` | [qwen_analysis.json.md](qwen_analysis.json.md) | `5a7f69758e82fe2b1e958847d1ad93adde8001eb12316a2947f71714b1eb4e49` |
| `evaluation/qwen_diagnostics.json` | [qwen_diagnostics.json.md](qwen_diagnostics.json.md) | `c9dd09b8c64ffc8d4ca20248e655589eb549837a65d1abcdd21e9f3ce46f7d4c` |
| `evaluation/qwen_diagnostics.py` | [qwen_diagnostics.py.md](qwen_diagnostics.py.md) | `f7f1c2b6035239842341913246fafc3d895dfda1fddcde4f40443c79a712a742` |
| `evaluation/qwen_english_analysis.json` | [qwen_english_analysis.json.md](qwen_english_analysis.json.md) | `eafba31b2fc232531591b75f52f56bca8232283b747b532c69971d77971b950d` |
| `evaluation/QWEN_ENGLISH_EVALUATION.md` | [QWEN_ENGLISH_EVALUATION.md](QWEN_ENGLISH_EVALUATION.md) | `d2084b39e46c320a29a3bfd86d39b3d27f16a7b63d8ddad50791bddd0f656fd0` |
| `evaluation/qwen_english_results.json` | [qwen_english_results.json.md](qwen_english_results.json.md) | `9950d1d367c428e317abc828b76d39a663101f66e0823449a2784c2f6eb2cfa4` |
| `evaluation/QWEN_EVALUATION.md` | [QWEN_EVALUATION.md](QWEN_EVALUATION.md) | `53580f70623bc6b2221ea252221f0c32c1a32d751a4b8f5bb1cf15327509aba0` |
| `evaluation/qwen_refill_results.json` | [qwen_refill_results.json.md](qwen_refill_results.json.md) | `0cc2270c2e4bc6437f1871ef611649bff9dd64899faec18ec802a269ed54c3ab` |
| `evaluation/qwen_refill_v2_results.json` | [qwen_refill_v2_results.json.md](qwen_refill_v2_results.json.md) | `9afcffccf35901a2efb3323e79c2fbaa9b26f464607d2048085494e512e38335` |
| `evaluation/qwen_stt_analysis.json` | [qwen_stt_analysis.json.md](qwen_stt_analysis.json.md) | `604bac8d4c03982b1e4a8948769fe0fb6d290e3fc6a8b3363355e0c6e7f6cfde` |
| `evaluation/QWEN_STT_EVALUATION.md` | [QWEN_STT_EVALUATION.md](QWEN_STT_EVALUATION.md) | `1128eab8f87ed7d77f17a17a922733e1a87bbd688ed98b0384b4d015a174a317` |
| `evaluation/qwen_stt_results.json` | [qwen_stt_results.json.md](qwen_stt_results.json.md) | `6650eeea3f641df7792c8cf1559c177f7184fbb99e4be78493a5da08fc5556af` |
| `evaluation/refill_qwen_eval.py` | [refill_qwen_eval.py.md](refill_qwen_eval.py.md) | `c0e01ad2228abb47636ac2e2181781174eca6032f583e731dfe93fd6e4436a8a` |
| `evaluation/stt_cases.py` | [stt_cases.py.md](stt_cases.py.md) | `c2ea4d87b674b41cb430e1452bffd8c8e1a5bdb3ad0ca81c146d4fbbf825dccf` |
| `evaluation/stt_manifest.json` | [stt_manifest.json.md](stt_manifest.json.md) | `ba33fe25856c7b5e2c5435ff66ff7e43170785f01c9dc0e01f86eee6d5fa133c` |
