# Offline model evaluation

검출·종류·잔량 모델의 오프라인 평가와 PyTorch / export 결과 비교 코드를 둔다.

- 이미지·정답·객체별 결과·실패 사례 비교
- 학습에 사용하지 않은 데이터 평가
- 동일 입력·전처리로 변환 전후 출력 비교
- 보드에서 수집한 실제 latency·메모리·delegation 기록 분석

대량 출력은 `models/` 하위 실험 폴더 등에 저장한다. 공유할 설정·요약 보고서는 `docs/`에 두고 모델·데이터 버전과 실행 위치를 명시한다. 생성된 설명용 사진과 fixture는 실측 정확도 자료로 취급하지 않는다.

과거 Qwen 텍스트·유사 STT 치환 평가 아카이브는 `docs/qwen_evaluation/`에 그대로 둔다. 앱의 unit/integration 테스트와 모델 정확도 평가는 구분한다.
