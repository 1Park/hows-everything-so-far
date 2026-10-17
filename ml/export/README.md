# Export and deployment bundle

학습 checkpoint 또는 제공 모델을 보드용 `.pte`로 export하는 코드·양자화·출력 검증·bundle 생성 도구를 둔다.

주최 측이 지원하는 QCS8275 checkout·QAIRT/QNN SDK·export 환경을 사용한다. 공식 최신 버전이나 다른 chipset target으로 임의 대체하지 않는다. Docker 환경 정의는 상위 `ml/`에 둔다.

입력 shape·dtype·layout·전처리·출력 계약을 확인하고, 필요한 calibration·양자화·QNN lowering·export를 수행한다. `.pte` 생성 성공과 실제 보드 실행·NPU delegation 검증은 별도 단계다.

결과는 `models/`의 버전별 bundle에 저장한다. 모델 파일 외에도 필요 시 tokenizer·labels·샘플 입력·reference 출력·metadata를 함께 준비한다. 보드 runtime 서버는 이 bundle을 설정 경로로 읽는다. export 도구를 프로덕션 서버에 포함하지 않는다.
