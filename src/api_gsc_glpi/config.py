# ======================================================
# CONFIGURAÇÕES GERAIS
# ======================================================

POLL_INTERVAL_SECONDS = 30

# ======================================================
# GLPI
# ======================================================

# URL base da API REST do GLPI (obrigatório terminar com /apirest.php)
GLPI_API_URL = "https://glpi-hmg.petacorp.com.br/apirest.php"

GLPI_APP_TOKEN = "UaSHwe2iiCvbP8gQmyl9yWWSTf59JNUSfODMp7q1"
GLPI_USER_TOKEN = "jSUU9OT2DvF67PPz5xG15aIqKID1gwTDCfKsvoBy"

# Categoria CAIXA (itilcategories_id)
GLPI_CATEGORIA_ID = 7

# Entidade padrão (entities_id)
GLPI_ENTITIES_ID = 6

# SSL
GLPI_VERIFY_SSL = False

# ======================================================
# CAIXA – WEBSERVICE SIGSC
# ======================================================

CAIXA_ENDPOINT = (
    "https://sigscint.caixa.gov.br/arsys/services/ARService"
    "?server=arsapphmp-int.caixa"
    "&webService=GSC_RF010_FornecedorExterno_V401_WS"
)

CAIXA_USER = "USR_PETACORP2"
CAIXA_PASSWORD = "PETACORP1234"
CAIXA_TOKEN = "IDGAA5V0F9OUSATDXCY3TCV2UTGOZL"

# ⚠️ Tem que ser o CPY (igual no Postman)
CAIXA_QUALIFICATION = "CPY000000075749"

CAIXA_TIMEOUT_SECONDS = 60

# ======================================================
# CAIXA – IDENTIFICAÇÃO DO FORNECEDOR (SIGSC)
# ======================================================

# ID do fornecedor no SIGSC (aparece no XML como <urn:idfornecedor>)
CAIXA_ID_FORNECEDOR = "SGP000000124811"

# Nome do fornecedor no SIGSC (aparece no XML como <urn:nomefornecedor>)
CAIXA_NOME_FORNECEDOR = "PETACORP"

# ======================================================
# COMPATIBILIDADE COM ARQUIVOS ANTIGOS (NÃO REMOVER)
# ======================================================

# Alguns arquivos antigos ainda usam GLPI_URL
GLPI_URL = GLPI_API_URL
