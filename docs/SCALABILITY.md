# TilinX — Escalabilidad Distribuida

## Estrategia Actual
- **Caché local** en `cache.py` con TTL en memoria (Python dict)
- **DB compartida** via `ips.json` en disco (NFS o bind mount)

## Opciones de Escalado

### 1. Redis como caché distribuida
- Reemplazar/integrar `cache.py` con Redis
- TTLs naturales de Redis
- Cluster: `redis-py-cluster`

```python
import redis
r = redis.Redis(host="redis-master", port=6379)
r.setex(f"uid:{uid}", 3600, status)
```

### 2. MySQL/PostgreSQL como DB central
- Migrar `ips.json` → tabla `ips`
- Elimina locking en escrituras concurrentes
- Soporta múltiples instancias del proxy simultáneamente

```sql
CREATE TABLE ips (
  ip VARCHAR(45) PRIMARY KEY,
  status VARCHAR(16),
  expires_at INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. Load Balancer
- Múltiples instancias del bot detrás de un balanceador
- Webhook mode de Telegram (en lugar de polling)
- Sesiones sticky para evitar race conditions

### 4. Proxy Pool
- Pool de conexiones SOCKS5/HTTP
- Rotación automática ante fallos
- Health checking periódico

## Roadmap
| Fase | Descripción | Prioridad |
|------|-------------|-----------|
| 1 | Redis para caché distribuida | Alta |
| 2 | PostgreSQL para uids | Alta |
| 3 | Load balancer + webhook mode | Media |
| 4 | Proxy pool con health checks | Baja |

## Configuración
```bash
# Redis
export TilinX_REDIS_HOST=redis-master
export TilinX_REDIS_PORT=6379
export TilinX_REDIS_DB=0

# PostgreSQL
export TilinX_DB_HOST=pg-master
export TilinX_DB_PORT=5432
export TilinX_DB_NAME=tilinx
export TilinX_DB_USER=tilinx
export TilinX_DB_PASS=changeme
```
