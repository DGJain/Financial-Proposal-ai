/**
 * @fpp/shared-types — the single contract surface shared by the Next.js frontend
 * and (mirrored from) the FastAPI backend.
 *
 * - `enums`   — value-level vocabulary mirroring app/domain StrEnums.
 * - `domain`  — entity/value-object shapes.
 * - `metrics` — dashboard / analytics shapes.
 * - `api`     — request/response DTOs generated from the backend OpenAPI spec
 *               (./api/generated.ts, produced by `pnpm gen:openapi`).
 */

export * from './enums/index.js';
export * from './enums/subtypes.js';
export * from './domain/index.js';
export * from './metrics/index.js';
