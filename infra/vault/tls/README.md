# TLS для prod-Vault

`vault.prod.hcl` слушает HTTPS и ждёт здесь `tls.crt` / `tls.key`. Их генерит **оператор** на
боевом сервере (в репозиторий НЕ коммитятся — см. `.gitignore`). Vault во внутренней сети, наружу
не публикуется, поэтому достаточно self-signed; control-plane ходит с `VAULT_SKIP_VERIFY=1`
(или, лучше, с `VAULT_CACERT`, указывающим на этот CA).

Сгенерировать self-signed (CN=vault, SAN для имени сервиса и localhost):

```sh
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout infra/vault/tls/tls.key -out infra/vault/tls/tls.crt -days 825 \
  -subj "/CN=vault" -addext "subjectAltName=DNS:vault,DNS:localhost,IP:127.0.0.1"
chmod 600 infra/vault/tls/tls.key
```

Для проверки сертификата вместо пропуска: положите CA рядом, смонтируйте и задайте
`VAULT_CACERT=/vault/tls/tls.crt`, `VAULT_SKIP_VERIFY=0` для control-plane.
