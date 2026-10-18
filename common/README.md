# Common

contracts.py: strict shared schema / bbox / IDs / drinks. Request interpretation uses only intent and item; requests that are not understood are not_understood. config.py: dotenv selection, process env precedence, range validation. api.py: structured logs/request IDs/error schema/bounded gate/raw body limit. media.py: transport signature and size validation only. backends.py: generic text backend and trusted external factory.

No dependencies on ML training, model preprocessing or GPIO. Follows the [contracts](../docs/CONTRACTS.md).
