# Shared development fixtures

보드나 모델 없이 같은 상황을 재현할 작은 이미지·짧은 영상·JSON 응답을 커밋하는 공간이다. 실제 샘플 payload는 공통 schema를 구현하면서 추가한다.

우선 준비할 상황:

- 여러 컵 중 물이 부족한 컵 → 물 소량 리필
- 음료 변경, 고객 거절·취소
- 충분한 잔량, 불확실한 판단
- 잘못된 모델 응답, timeout·장면 변경·오래된 확인

fixture마다 scene/object/request ID와 출처·생성 여부를 기록한다. bbox·라벨·점수를 임의 작성했다면 mock임을 표시한다. fixture는 실제 정확도나 보드 성능 증거가 아니다. 대량 데이터는 `data/`, 실제 가중치는 `models/`에 둔다. 문서 설명용 사진은 기존 `docs/assets/`에 유지한다.
