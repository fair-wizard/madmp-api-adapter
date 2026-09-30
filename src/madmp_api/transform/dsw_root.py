"""Question/answer identifiers of the Common DSW Knowledge Model.

Captured from ``dsw:root:2.7.0`` (see ``example/knowledge-models``). Reply
paths are dot-joined UUIDs: ``chapter.question`` for plain questions and
``chapter.list.item.question`` for items of a list question.
"""

# --- Administrative information -------------------------------------
CH_ADMIN = '1e85da40-bbfc-4180-903e-6c569ed2da38'

Q_CONTRIBUTORS = '73d686bd-7939-412e-8631-502ee6d9ea7b'
Q_CONTRIB_NAME = '6155ad47-3d1e-4488-9f2a-742de1e56580'
Q_CONTRIB_EMAIL = '3a2ffc13-6a0e-4976-bb34-14ab6d938348'
Q_CONTRIB_ORCID = '6295a55d-48d7-4f3c-961a-45b38eeea41f'
Q_CONTRIB_AFFILIATION = '68530470-1f1c-4448-8593-63a288713a66'
Q_CONTRIB_ROLE = '829dcda6-db8a-40ac-819a-92b9b52490f5'

Q_PROJECTS = 'c3dabaaf-c946-4a0d-889c-ede966f97667'
Q_PROJ_NAME = 'f0ef08fd-d733-465c-bc66-5de0b826c41b'
Q_PROJ_ABSTRACT = '22583d74-3c98-4e0a-b363-26d767c88212'
Q_PROJ_START = 'de84b9b5-bcd0-4954-8370-72ea83916b8c'
Q_PROJ_END = 'cabc6f07-6015-454e-b97a-c34db4ec0c60'

Q_FUNDING = '36a87eac-402d-43fb-a0df-ac5963bdf87d'
Q_FUNDER = '0b12fb8c-ee0f-40c0-9c53-b6826b786a0c'
Q_FUNDING_STATUS = '54ff3b18-652f-4235-8f9f-3c87e2d63169'
Q_GRANT = '1ccbd0bb-4263-4240-9dc5-936ef09eef53'

Q_COSTS = '353eeaca-45fa-4958-a33c-ec6de3075701'
Q_COST_TITLE = '7098b454-bc5e-4f83-a95d-970aa42e1479'
Q_COST_DESCRIPTION = 'b3d9b6ca-bd24-4fa3-a3bd-d15005b9ae8b'
Q_COST_CURRENCY = 'ac1f8f04-17a2-49e9-b2ad-2a9f8e44efb3'
Q_COST_AMOUNT = 'e53fdad9-7799-4eb4-8b4d-fa9aa05f9d2d'

# --- Creating and collecting data ------------------------------------
CH_COLLECT = 'b1df3c74-0b1f-4574-81c4-4cc2d780c1af'
Q_ETHICAL = 'ebcbf4c6-ce25-4a0b-9e82-039a88498203'
A_ETHICAL_NO = '579c0a9a-29f0-4ab8-991d-bc4f55f2e4b8'
A_ETHICAL_YES = '9310b639-4cf7-4f94-8fbe-c1afc50afe4b'

# --- Preserving data --------------------------------------------------
CH_PRESERVE = 'd5b27482-b598-4b8c-b534-417d4ad27394'
Q_DATASETS = '4e0c1edf-660c-4ebf-81f5-9fa959dead30'
Q_DS_TITLE = 'b0949d09-d179-4491-9fb4-14b0deb9f862'
Q_DS_DESCRIPTION = '205a886d-83d7-4359-ae63-7103e05357c3'
Q_DS_TYPE = '3a8ed3fc-b1a6-4119-80ed-238804861734'
Q_DS_IDENTIFIERS = 'cf727a0a-78c4-45a7-aa9b-cf7650ae873a'
Q_DS_ID_TYPE = '5c22cf59-89e3-43a1-af10-1af43a97bcb2'
Q_DS_ID_VALUE = '9e13b2d3-5f00-4e19-8a52-5c33c5b1cb07'
Q_DS_PERSONAL = 'a1d76760-053c-4706-80a2-cfb6c6a061f3'
A_PERSONAL_NO = '4b2a08c7-4942-41fc-8114-d3868c882624'
A_PERSONAL_YES = '0cdc4817-7c54-4ec1-b2f4-5c007a85c7b8'
Q_DS_SENSITIVE = 'cc95b399-7d8d-4232-bccf-686f78c91bff'
A_SENSITIVE_NO = '60de66a3-d303-4784-8931-bc58f8a3e747'
A_SENSITIVE_YES = '2686575d-cd74-4e2c-8524-eaca6f510425'

# --- Vocabularies -----------------------------------------------------
ID_TYPE_ANSWERS = {
    'b93a037a-006a-486f-87e0-6bef5c28879b': 'handle',
    '48062bc9-0ffb-4509-bec6-e90641a30569': 'doi',
    'c353f027-823b-4242-9149-37dca26cf4bc': 'ark',
    '7a1d3b28-5f85-48b8-b052-2448c276d9fc': 'url',
    '97236701-7b62-40f8-99a0-3b18d3fe3658': 'other',
}
ID_TYPE_TO_ANSWER = {v: k for k, v in ID_TYPE_ANSWERS.items()}

FUNDING_STATUS_ANSWERS = {
    '59ed0193-8211-4ee8-8d36-0640d99ce870': 'planned',
    '85fad342-a89d-414b-bc83-286a7417bb78': 'applied',
    'dcbeab22-d188-4fa0-b50b-5c9d1a2fbefe': 'granted',
    '8c0c9f28-4672-46ba-a939-48c2c892d790': 'rejected',
}
FUNDING_STATUS_TO_ANSWER = {v: k for k, v in FUNDING_STATUS_ANSWERS.items()}

ROLE_CHOICES = {
    '2c6ee59d-4dc9-4dcb-ac13-d969c317a117': 'ContactPerson',
    'fc789e2d-01ee-432d-82f9-1b659f58eaf8': 'DataCollector',
    '618cb529-0c24-4762-a739-7983004d1b2b': 'DataCurator',
    '627ab8dc-8026-498d-ba7a-3df122e29ede': 'DataManager',
    'bc82b138-9816-46dd-8ff8-cea2826a3ad4': 'DataProtectionOfficer',
    '3022098b-0e2c-4fad-9f28-cf2e1325521d': 'DataSteward',
    '27dccf06-3b67-4c75-8888-6549e4da2d31': 'Distributor',
    '100daf28-b55e-4b04-8295-f2aa83d0c734': 'Editor',
    '2085d67e-e144-4ec2-a788-1b26ac1cd7ab': 'Producer',
    '2d433965-55e3-4540-aae4-f85639d4e4fc': 'ProjectLeader',
    'cd2d1e0d-c5ad-4d0e-afa2-5ed143323cb7': 'ProjectManager',
    '3d166766-6511-407b-a3e9-9565628fe05a': 'ProjectMember',
    'c81c63b6-bec0-4e12-b9cd-247fa4338c1f': 'Researcher',
    '704ebc65-6932-4679-bbe5-f25c19843f0f': 'RightsHolder',
    '374b887f-dfd8-4763-b360-b2a8aa12051c': 'Sponsor',
    '6dfde2b6-4234-47a0-b7da-ccb7412f8490': 'Supervisor',
    'ce5476ed-5cc3-42ff-ac9d-d567f28cc2a6': 'WorkPackageLeader',
    '21047dec-71ee-40e4-868a-3ed75a027ff6': 'CreatorOfDMP',
    'e957ecd5-baa2-4a3c-aaf1-735d416e5e11': 'Other',
}
ROLE_TO_CHOICE = {v: k for k, v in ROLE_CHOICES.items()}
