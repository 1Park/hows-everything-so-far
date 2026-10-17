# Local model assets

다운로드한 모델·checkpoint·`.pte`·tokenizer·학습 및 export 산출물을 저장한다. 이 README만 Git에 포함하며 나머지 파일·하위 폴더는 제외한다.

예시 저장 구조이며 아직 실제 bundle은 없다:

```text
models/
  dino/<version>/     모델·labels·전처리/출력 metadata·reference 입력/출력
  qwen/<version>/     모델·tokenizer·chat template/생성 규격·metadata
  detector/<version>/ 검출 모델·라벨·입출력 규격
  experiments/       checkpoint·오프라인 평가 산출물
```

모델 출처·버전·checksum·획득 방법·보드 target·ExecuTorch/SDK 버전은 공유 문서 또는 `ml/configs/`에 기록한다. 서버는 설정으로 경로를 받으며 각 개발자의 절대 경로를 코드에 박지 않는다. 실제 보드 bundle 규격은 제공 파일을 확인한 뒤 확정한다.
