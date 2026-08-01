-- 智慧長照 AI 陪伴系統 PostgreSQL Schema v0.1
-- 內容：48 張表、ENUM、PK/FK、CHECK/UNIQUE/INDEX、Trigger、Table/Column Comments
-- 欄位說明使用 COMMENT ON TABLE / COMMENT ON COLUMN，匯入 DBeaver、DataGrip 等工具後可在資料庫物件與 ER 圖設定中顯示。
-- 本檔建議作為一次性初始化或 Alembic baseline；後續變更請以 Migration 管理。

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS eldercare_ai;
SET search_path TO eldercare_ai, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'actor_type_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.actor_type_enum AS ENUM ('ELDER', 'DAYCARE_CARE_WORKER', 'HOME_CARE_WORKER', 'FAMILY_MEMBER', 'ADMIN', 'CONTENT_MANAGER', 'SYSTEM_SERVICE');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.actor_type_enum IS '系統操作主體類型。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'tenant_type_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.tenant_type_enum AS ENUM ('CARE_ORGANIZATION', 'COMMUNITY_ORGANIZATION', 'HOME_CARE_PROVIDER', 'DEMO');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.tenant_type_enum IS '租戶或營運單位類型。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'care_unit_type_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.care_unit_type_enum AS ENUM ('DAYCARE_CENTER', 'COMMUNITY_SITE', 'HOME_CARE_AGENCY');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.care_unit_type_enum IS '照護單位類型。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'relationship_type_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.relationship_type_enum AS ENUM ('DAYCARE_ASSIGNMENT', 'HOME_CARE_ASSIGNMENT', 'FAMILY_SHARE', 'LEGAL_REPRESENTATIVE');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.relationship_type_enum IS 'Actor 與長者之間的授權關係類型。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'language_code_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.language_code_enum AS ENUM ('ZH_TW', 'NAN_TW', 'HAK_TW', 'EN_US', 'MIXED', 'UNKNOWN');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.language_code_enum IS '系統支援的語言路由代碼。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'notification_channel_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.notification_channel_enum AS ENUM ('LINE', 'EMAIL', 'IN_APP');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.notification_channel_enum IS '家屬通知通路。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'report_type_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.report_type_enum AS ENUM ('DAILY', 'WEEKLY', 'MONTHLY', 'IMPORTANT_EVENT');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.report_type_enum IS '家屬報表週期或類型。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'review_decision_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.review_decision_enum AS ENUM ('VERIFY', 'CORRECT', 'REJECT', 'EXCLUDE', 'REQUEST_MORE_INFO');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.review_decision_enum IS '人工覆核決策。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'data_classification_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.data_classification_enum AS ENUM ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.data_classification_enum IS '資料敏感度分級。';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE t.typname = 'source_kind_enum' AND n.nspname = 'eldercare_ai') THEN
        CREATE TYPE eldercare_ai.source_kind_enum AS ENUM ('DOCUMENT', 'WEB_PAGE', 'DATASET', 'POLICY', 'SCALE', 'MANUAL', 'OTHER');
    END IF;
END
$$;
COMMENT ON TYPE eldercare_ai.source_kind_enum IS '知識來源類型。';

CREATE TABLE eldercare_ai.actor (
    actor_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type eldercare_ai.actor_type_enum NOT NULL,
    cognito_sub VARCHAR(200),
    display_name VARCHAR(120) NOT NULL,
    email VARCHAR(254),
    phone VARCHAR(32),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED','DELETED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_actor_cognito_sub UNIQUE (cognito_sub)
);
COMMENT ON TABLE eldercare_ai.actor IS '保存長者、照護者、家屬、管理者與系統服務等可操作主體。';
COMMENT ON COLUMN eldercare_ai.actor.actor_id IS '操作主體唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.actor.actor_type IS '操作主體類型。';
COMMENT ON COLUMN eldercare_ai.actor.cognito_sub IS 'Amazon Cognito 或外部身分系統的 Subject ID。';
COMMENT ON COLUMN eldercare_ai.actor.display_name IS '畫面顯示名稱。';
COMMENT ON COLUMN eldercare_ai.actor.email IS '電子郵件；家屬、照護者或管理者可使用。';
COMMENT ON COLUMN eldercare_ai.actor.phone IS '聯絡電話；需依角色與授權遮罩。';
COMMENT ON COLUMN eldercare_ai.actor.status IS '帳號狀態。';
COMMENT ON COLUMN eldercare_ai.actor.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.actor.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.tenant (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_type eldercare_ai.tenant_type_enum NOT NULL,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED','DELETED')),
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Taipei',
    default_policy_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.tenant IS '代表照護機構、營運單位或 Demo 資料隔離邊界。';
COMMENT ON COLUMN eldercare_ai.tenant.tenant_id IS '租戶唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.tenant.tenant_type IS '租戶類型。';
COMMENT ON COLUMN eldercare_ai.tenant.name IS '租戶名稱。';
COMMENT ON COLUMN eldercare_ai.tenant.status IS '租戶狀態。';
COMMENT ON COLUMN eldercare_ai.tenant.timezone IS '租戶預設時區。';
COMMENT ON COLUMN eldercare_ai.tenant.default_policy_id IS '租戶預設 Policy；FK 於 policy_registry 建立後補上。';
COMMENT ON COLUMN eldercare_ai.tenant.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.tenant.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.care_unit (
    care_unit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    unit_type eldercare_ai.care_unit_type_enum NOT NULL,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','CLOSED')),
    address_text TEXT,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Taipei',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_care_unit_name UNIQUE (tenant_id, name)
);
COMMENT ON TABLE eldercare_ai.care_unit IS '代表日照中心、社區據點、居家服務單位或照護群組。';
COMMENT ON COLUMN eldercare_ai.care_unit.care_unit_id IS '照護單位唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.care_unit.tenant_id IS '所屬租戶。';
COMMENT ON COLUMN eldercare_ai.care_unit.unit_type IS '照護單位類型。';
COMMENT ON COLUMN eldercare_ai.care_unit.name IS '照護單位名稱。';
COMMENT ON COLUMN eldercare_ai.care_unit.status IS '照護單位狀態。';
COMMENT ON COLUMN eldercare_ai.care_unit.address_text IS '地址文字；敏感顯示需依權限。';
COMMENT ON COLUMN eldercare_ai.care_unit.timezone IS '照護單位時區。';
COMMENT ON COLUMN eldercare_ai.care_unit.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.care_unit.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.actor_tenant_membership (
    membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    care_unit_id UUID REFERENCES eldercare_ai.care_unit(care_unit_id),
    role_code VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','EXPIRED','REVOKED')),
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_membership_period CHECK (effective_to IS NULL OR effective_to > effective_from)
);
COMMENT ON TABLE eldercare_ai.actor_tenant_membership IS '定義 Actor 在某租戶或照護單位中的角色與有效期間。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.membership_id IS '成員關係唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.actor_id IS '操作主體。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.tenant_id IS '所屬租戶。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.care_unit_id IS '限制到特定照護單位；可空。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.role_code IS '租戶內角色代碼。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.status IS '成員關係狀態。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.effective_from IS '開始生效時間。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.effective_to IS '失效時間；空值代表未預定失效。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.actor_tenant_membership.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.elder (
    elder_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    primary_care_unit_id UUID REFERENCES eldercare_ai.care_unit(care_unit_id),
    display_name VARCHAR(120) NOT NULL,
    primary_care_setting VARCHAR(32) NOT NULL CHECK (primary_care_setting IN ('DAYCARE','COMMUNITY','HOME_CARE','INDEPENDENT')),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','DECEASED','DELETED')),
    preferred_language eldercare_ai.language_code_enum NOT NULL DEFAULT 'ZH_TW',
    preferred_name VARCHAR(80),
    response_length_preference VARCHAR(20) NOT NULL DEFAULT 'STANDARD' CHECK (response_length_preference IN ('SHORT','STANDARD','DETAILED')),
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Taipei',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.elder IS '保存長者基本資料、語言偏好、介面偏好與主要照護場域。';
COMMENT ON COLUMN eldercare_ai.elder.elder_id IS '長者唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.elder.tenant_id IS '長者所屬資料隔離租戶。';
COMMENT ON COLUMN eldercare_ai.elder.primary_care_unit_id IS '主要照護單位；居家照護可空。';
COMMENT ON COLUMN eldercare_ai.elder.display_name IS 'Demo 或去識別化顯示名稱。';
COMMENT ON COLUMN eldercare_ai.elder.primary_care_setting IS '主要照護場域。';
COMMENT ON COLUMN eldercare_ai.elder.status IS '長者帳戶或服務狀態。';
COMMENT ON COLUMN eldercare_ai.elder.preferred_language IS '主要語言偏好。';
COMMENT ON COLUMN eldercare_ai.elder.preferred_name IS 'AI 回覆時使用的偏好稱呼。';
COMMENT ON COLUMN eldercare_ai.elder.response_length_preference IS '預設回覆長度偏好。';
COMMENT ON COLUMN eldercare_ai.elder.timezone IS '長者所在地時區。';
COMMENT ON COLUMN eldercare_ai.elder.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.elder.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.care_relationship (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    care_unit_id UUID REFERENCES eldercare_ai.care_unit(care_unit_id),
    relationship_type eldercare_ai.relationship_type_enum NOT NULL,
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','EXPIRED','REVOKED')),
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_care_relationship_period CHECK (effective_to IS NULL OR effective_to > effective_from)
);
COMMENT ON TABLE eldercare_ai.care_relationship IS '定義 Actor 與長者之間的授權關係、作用範圍與有效期間。';
COMMENT ON COLUMN eldercare_ai.care_relationship.relationship_id IS '照護或分享關係唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.care_relationship.elder_id IS '被授權存取的長者。';
COMMENT ON COLUMN eldercare_ai.care_relationship.actor_id IS '取得關係授權的 Actor。';
COMMENT ON COLUMN eldercare_ai.care_relationship.tenant_id IS '關係所屬租戶。';
COMMENT ON COLUMN eldercare_ai.care_relationship.care_unit_id IS '關係限制的照護單位；可空。';
COMMENT ON COLUMN eldercare_ai.care_relationship.relationship_type IS '關係類型。';
COMMENT ON COLUMN eldercare_ai.care_relationship.scope IS '可讀欄位、允許動作與用途範圍。';
COMMENT ON COLUMN eldercare_ai.care_relationship.status IS '關係狀態。';
COMMENT ON COLUMN eldercare_ai.care_relationship.effective_from IS '開始生效時間。';
COMMENT ON COLUMN eldercare_ai.care_relationship.effective_to IS '結束時間；空值代表未預定失效。';
COMMENT ON COLUMN eldercare_ai.care_relationship.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.care_relationship.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.knowledge_source (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_tenant_id UUID REFERENCES eldercare_ai.tenant(tenant_id),
    registered_by_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    source_kind eldercare_ai.source_kind_enum NOT NULL,
    title VARCHAR(500) NOT NULL,
    source_agency VARCHAR(160),
    public_url TEXT,
    license_status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN' CHECK (license_status IN ('PUBLIC','AUTHORIZED','RESTRICTED','UNKNOWN')),
    review_status VARCHAR(32) NOT NULL DEFAULT 'NEEDS_REVIEW' CHECK (review_status IN ('NEEDS_REVIEW','REVIEWED','REJECTED','EXPIRED')),
    data_classification eldercare_ai.data_classification_enum NOT NULL DEFAULT 'PUBLIC',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.knowledge_source IS '登錄法規、衛教、量表、工作手冊與其他可信來源。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.source_id IS '來源唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.owner_tenant_id IS '私有來源所屬租戶；公開來源可空。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.registered_by_actor_id IS '登錄來源的管理者。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.source_kind IS '來源種類。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.title IS '來源標題。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.source_agency IS '發布機關或來源單位。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.public_url IS '公開來源網址。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.license_status IS '授權狀態。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.review_status IS '來源審查狀態。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.data_classification IS '資料敏感度。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.knowledge_source.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.knowledge_source_version (
    source_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES eldercare_ai.knowledge_source(source_id),
    previous_version_id UUID REFERENCES eldercare_ai.knowledge_source_version(source_version_id),
    version_label VARCHAR(80) NOT NULL,
    effective_date DATE,
    published_at TIMESTAMPTZ,
    file_uri TEXT,
    sha256 CHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','SUPERSEDED','EXPIRED','REJECTED')),
    uploaded_by_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_knowledge_source_version UNIQUE (source_id, version_label)
);
COMMENT ON TABLE eldercare_ai.knowledge_source_version IS '保存每份可信來源的實際版本、檔案、日期與雜湊。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.source_version_id IS '來源版本唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.source_id IS '所屬來源。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.previous_version_id IS '前一版本；首版可空。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.version_label IS '來源版本標籤。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.effective_date IS '內容生效日期。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.published_at IS '來源發布時間。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.file_uri IS 'S3 或受控儲存位置。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.sha256 IS '來源檔案 SHA-256。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.metadata IS '地區、服務類型、適用對象等 Metadata。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.status IS '來源版本狀態。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.uploaded_by_actor_id IS '上傳或建立版本的人員。';
COMMENT ON COLUMN eldercare_ai.knowledge_source_version.created_at IS '版本建立時間。';

CREATE TABLE eldercare_ai.policy_registry (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_tenant_id UUID REFERENCES eldercare_ai.tenant(tenant_id),
    policy_code VARCHAR(120) NOT NULL,
    policy_type VARCHAR(40) NOT NULL CHECK (policy_type IN ('CONSENT','RETENTION','ELIGIBILITY','SAFETY','SCALE_SCORING','RISK_RULE','ROUTING','OTHER')),
    version VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','RETIRED','REJECTED')),
    source_version_id UUID REFERENCES eldercare_ai.knowledge_source_version(source_version_id),
    policy_payload JSONB NOT NULL,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    approved_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_policy_period CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);
COMMENT ON TABLE eldercare_ai.policy_registry IS '保存同意、保存期限、安全、Eligibility、風險與量表規則版本。';
COMMENT ON COLUMN eldercare_ai.policy_registry.policy_id IS 'Policy 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.policy_registry.owner_tenant_id IS '租戶自訂 Policy 所屬租戶；全域 Policy 可空。';
COMMENT ON COLUMN eldercare_ai.policy_registry.policy_code IS '穩定 Policy 代碼。';
COMMENT ON COLUMN eldercare_ai.policy_registry.policy_type IS 'Policy 類型。';
COMMENT ON COLUMN eldercare_ai.policy_registry.version IS 'Policy 版本。';
COMMENT ON COLUMN eldercare_ai.policy_registry.status IS 'Policy 狀態。';
COMMENT ON COLUMN eldercare_ai.policy_registry.source_version_id IS 'Policy 的可信文件來源；可空。';
COMMENT ON COLUMN eldercare_ai.policy_registry.policy_payload IS '機器可執行或可驗證的 Policy 內容。';
COMMENT ON COLUMN eldercare_ai.policy_registry.effective_from IS '開始生效時間。';
COMMENT ON COLUMN eldercare_ai.policy_registry.effective_to IS '停止生效時間。';
COMMENT ON COLUMN eldercare_ai.policy_registry.approved_by_actor_id IS '核准 Policy 的管理者。';
COMMENT ON COLUMN eldercare_ai.policy_registry.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.policy_registry.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.consent_grant (
    consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    purpose_code VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'GRANTED' CHECK (status IN ('PENDING','GRANTED','REVOKED','EXPIRED','REJECTED')),
    version INTEGER NOT NULL CHECK (version > 0),
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    granted_by_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    policy_id UUID NOT NULL REFERENCES eldercare_ai.policy_registry(policy_id),
    granted_at TIMESTAMPTZ,
    effective_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_consent_purpose_version UNIQUE (elder_id, purpose_code, version),
    CONSTRAINT ck_consent_period CHECK (expires_at IS NULL OR expires_at > effective_at)
);
COMMENT ON TABLE eldercare_ai.consent_grant IS '保存錄音、逐字稿、事件擷取、記憶、主動陪伴與家屬分享的分層同意。';
COMMENT ON COLUMN eldercare_ai.consent_grant.consent_id IS '同意紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.consent_grant.elder_id IS '授權用途所屬長者。';
COMMENT ON COLUMN eldercare_ai.consent_grant.purpose_code IS '同意用途代碼，例如 BASIC_VOICE 或 LONG_TERM_MEMORY。';
COMMENT ON COLUMN eldercare_ai.consent_grant.status IS '同意狀態。';
COMMENT ON COLUMN eldercare_ai.consent_grant.version IS '同一用途的版本號。';
COMMENT ON COLUMN eldercare_ai.consent_grant.scope IS '授權資料範圍、分享範圍與限制。';
COMMENT ON COLUMN eldercare_ai.consent_grant.granted_by_actor_id IS '同意者或合法代理人。';
COMMENT ON COLUMN eldercare_ai.consent_grant.policy_id IS '同意文字與規則版本。';
COMMENT ON COLUMN eldercare_ai.consent_grant.granted_at IS '完成同意時間。';
COMMENT ON COLUMN eldercare_ai.consent_grant.effective_at IS '開始生效時間。';
COMMENT ON COLUMN eldercare_ai.consent_grant.expires_at IS '到期時間。';
COMMENT ON COLUMN eldercare_ai.consent_grant.revoked_at IS '撤回時間。';
COMMENT ON COLUMN eldercare_ai.consent_grant.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.consent_grant.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.conversation_session (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    initiator_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    initiator_type VARCHAR(24) NOT NULL CHECK (initiator_type IN ('ELDER','CAREGIVER','FAMILY','SYSTEM')),
    language_route eldercare_ai.language_code_enum NOT NULL,
    state VARCHAR(24) NOT NULL DEFAULT 'CREATED' CHECK (state IN ('CREATED','RECORDING','PROCESSING','RESPONDING','COMPLETED','CANCELLED','FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    trace_id VARCHAR(80) NOT NULL,
    consent_id UUID NOT NULL REFERENCES eldercare_ai.consent_grant(consent_id),
    consent_version INTEGER NOT NULL,
    policy_version VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_conversation_trace UNIQUE (trace_id),
    CONSTRAINT ck_conversation_period CHECK (ended_at IS NULL OR ended_at >= started_at)
);
COMMENT ON TABLE eldercare_ai.conversation_session IS '保存單次長者互動 Session 的狀態、語言路由、追蹤與同意快照。';
COMMENT ON COLUMN eldercare_ai.conversation_session.session_id IS '對話 Session 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.conversation_session.elder_id IS '互動長者。';
COMMENT ON COLUMN eldercare_ai.conversation_session.tenant_id IS '資料隔離租戶。';
COMMENT ON COLUMN eldercare_ai.conversation_session.initiator_actor_id IS '主動或回應式互動發起者；系統發起可空。';
COMMENT ON COLUMN eldercare_ai.conversation_session.initiator_type IS '互動發起類型。';
COMMENT ON COLUMN eldercare_ai.conversation_session.language_route IS '本次 Session 使用的語音路由。';
COMMENT ON COLUMN eldercare_ai.conversation_session.state IS 'Session 狀態。';
COMMENT ON COLUMN eldercare_ai.conversation_session.started_at IS '開始時間。';
COMMENT ON COLUMN eldercare_ai.conversation_session.ended_at IS '結束時間。';
COMMENT ON COLUMN eldercare_ai.conversation_session.trace_id IS '跨 ASR、Agent、TTS、儲存與背景工作的追蹤 ID。';
COMMENT ON COLUMN eldercare_ai.conversation_session.consent_id IS '本次處理使用的同意紀錄。';
COMMENT ON COLUMN eldercare_ai.conversation_session.consent_version IS '本次處理使用的同意版本快照。';
COMMENT ON COLUMN eldercare_ai.conversation_session.policy_version IS '本次對話使用的主要 Policy 版本。';
COMMENT ON COLUMN eldercare_ai.conversation_session.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.conversation_session.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.agent_run (
    agent_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES eldercare_ai.conversation_session(session_id),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    parent_agent_run_id UUID REFERENCES eldercare_ai.agent_run(agent_run_id),
    agent_id VARCHAR(120) NOT NULL,
    agent_version VARCHAR(64) NOT NULL,
    result_status VARCHAR(32) NOT NULL CHECK (result_status IN ('SUCCESS','NEEDS_CLARIFICATION','BLOCKED','HUMAN_REVIEW','NO_DATA','SCHEMA_FAILED','DEPENDENCY_FAILED','TIME_BUDGET_EXCEEDED','COST_BUDGET_EXCEEDED','CANCELLED')),
    model_id VARCHAR(200),
    prompt_version VARCHAR(80),
    policy_version VARCHAR(80),
    latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    token_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    stop_reason VARCHAR(160),
    trace_id VARCHAR(80) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_agent_run_period CHECK (completed_at IS NULL OR completed_at >= started_at)
);
COMMENT ON TABLE eldercare_ai.agent_run IS '保存每次 Agent 執行的模型、Prompt、結果、延遲、成本與停止原因。';
COMMENT ON COLUMN eldercare_ai.agent_run.agent_run_id IS 'Agent 執行唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.agent_run.session_id IS '所屬對話 Session；背景工作可空。';
COMMENT ON COLUMN eldercare_ai.agent_run.elder_id IS '本次執行的長者資料範圍。';
COMMENT ON COLUMN eldercare_ai.agent_run.tenant_id IS '本次執行的租戶範圍。';
COMMENT ON COLUMN eldercare_ai.agent_run.actor_id IS '觸發本次執行的 Actor。';
COMMENT ON COLUMN eldercare_ai.agent_run.parent_agent_run_id IS '父 Agent 執行；Orchestrator Handoff 時使用。';
COMMENT ON COLUMN eldercare_ai.agent_run.agent_id IS 'Agent 穩定識別名稱。';
COMMENT ON COLUMN eldercare_ai.agent_run.agent_version IS 'Agent 程式或設定版本。';
COMMENT ON COLUMN eldercare_ai.agent_run.result_status IS 'Agent 執行結果。';
COMMENT ON COLUMN eldercare_ai.agent_run.model_id IS '實際使用的 Bedrock 或自建模型 ID。';
COMMENT ON COLUMN eldercare_ai.agent_run.prompt_version IS 'Prompt 版本。';
COMMENT ON COLUMN eldercare_ai.agent_run.policy_version IS '主要 Policy 版本。';
COMMENT ON COLUMN eldercare_ai.agent_run.latency_ms IS '總延遲毫秒數。';
COMMENT ON COLUMN eldercare_ai.agent_run.token_usage IS '輸入、輸出與總 Token 使用量。';
COMMENT ON COLUMN eldercare_ai.agent_run.stop_reason IS '停止、阻擋或失敗原因。';
COMMENT ON COLUMN eldercare_ai.agent_run.trace_id IS '跨服務 Trace ID。';
COMMENT ON COLUMN eldercare_ai.agent_run.started_at IS '開始時間。';
COMMENT ON COLUMN eldercare_ai.agent_run.completed_at IS '完成時間。';
COMMENT ON COLUMN eldercare_ai.agent_run.created_at IS '紀錄建立時間。';

CREATE TABLE eldercare_ai.safety_evaluation (
    safety_evaluation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id UUID REFERENCES eldercare_ai.agent_run(agent_run_id),
    policy_id UUID NOT NULL REFERENCES eldercare_ai.policy_registry(policy_id),
    target_type VARCHAR(64) NOT NULL,
    target_id UUID,
    decision VARCHAR(24) NOT NULL CHECK (decision IN ('ALLOW','BLOCK','HUMAN_REVIEW','REDACT')),
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.safety_evaluation IS '保存醫療邊界、個資、Prompt Injection、分享與內容安全判斷。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.safety_evaluation_id IS '安全評估唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.agent_run_id IS '觸發安全評估的 Agent Run。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.policy_id IS '使用的安全 Policy。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.target_type IS '評估目標類型，例如 agent_output、summary 或 report。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.target_id IS '評估目標 ID；尚未正式建立時可空。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.decision IS '安全判斷結果。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.reason_codes IS '觸發的安全理由碼。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.flags IS 'PII、醫療紅線、分享限制等詳細旗標。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.reviewed_by_actor_id IS '人工覆核者；未人工覆核可空。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.evaluated_at IS '評估時間。';
COMMENT ON COLUMN eldercare_ai.safety_evaluation.created_at IS '紀錄建立時間。';

CREATE TABLE eldercare_ai.idempotency_record (
    idempotency_key VARCHAR(160) PRIMARY KEY,
    actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    tenant_id UUID REFERENCES eldercare_ai.tenant(tenant_id),
    request_fingerprint CHAR(64) NOT NULL,
    resource_type VARCHAR(64),
    resource_id UUID,
    status VARCHAR(20) NOT NULL CHECK (status IN ('IN_PROGRESS','COMPLETED','FAILED','EXPIRED')),
    response_status INTEGER,
    response_body_hash CHAR(64),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.idempotency_record IS '保存 API、Command、通知與背景工作冪等狀態，防止重複建立。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.idempotency_key IS '業務冪等鍵。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.actor_id IS '發出請求的 Actor。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.tenant_id IS '請求所屬租戶。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.request_fingerprint IS '請求內容雜湊，用於偵測同 Key 不同請求。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.resource_type IS '成功建立的資源類型。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.resource_id IS '成功建立的資源 ID。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.status IS '冪等處理狀態。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.response_status IS '首次完成請求的 HTTP 或業務狀態碼。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.response_body_hash IS '回應內容雜湊；避免保存敏感完整回應。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.expires_at IS '冪等紀錄到期時間。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.idempotency_record.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.agent_tool_call (
    tool_call_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id UUID NOT NULL REFERENCES eldercare_ai.agent_run(agent_run_id),
    actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    idempotency_key VARCHAR(160) REFERENCES eldercare_ai.idempotency_record(idempotency_key),
    tool_name VARCHAR(120) NOT NULL,
    tool_version VARCHAR(40) NOT NULL,
    request_payload JSONB NOT NULL,
    result_status VARCHAR(24) NOT NULL CHECK (result_status IN ('SUCCESS','BLOCKED','FAILED','TIMEOUT','CANCELLED')),
    response_payload JSONB,
    reason_code VARCHAR(120),
    retryable BOOLEAN NOT NULL DEFAULT false,
    trace_id VARCHAR(80) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_tool_call_period CHECK (completed_at IS NULL OR completed_at >= started_at)
);
COMMENT ON TABLE eldercare_ai.agent_tool_call IS '保存 Agent 工具呼叫、允許範圍、請求、結果與錯誤。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.tool_call_id IS 'Tool Call 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.agent_run_id IS '所屬 Agent Run。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.actor_id IS '代表其權限執行 Tool 的 Actor。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.idempotency_key IS '寫入型 Tool 使用的冪等鍵。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.tool_name IS '工具名稱。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.tool_version IS '工具 Contract 版本。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.request_payload IS '工具輸入；不得包含未授權完整敏感資料。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.result_status IS '工具執行結果。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.response_payload IS '工具輸出或安全縮減後內容。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.reason_code IS '阻擋或失敗理由碼。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.retryable IS '是否允許重試。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.trace_id IS '跨服務 Trace ID。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.started_at IS '開始時間。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.completed_at IS '完成時間。';
COMMENT ON COLUMN eldercare_ai.agent_tool_call.created_at IS '紀錄建立時間。';

CREATE TABLE eldercare_ai.context_manifest (
    context_manifest_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id UUID REFERENCES eldercare_ai.agent_run(agent_run_id),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    session_id UUID REFERENCES eldercare_ai.conversation_session(session_id),
    manifest JSONB NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.context_manifest IS '記錄某輪實際注入的 Persona、事件、記憶、RAG Chunk 與 Graph 關係。';
COMMENT ON COLUMN eldercare_ai.context_manifest.context_manifest_id IS 'Context Manifest 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.context_manifest.agent_run_id IS '使用此 Context 的 Agent Run。';
COMMENT ON COLUMN eldercare_ai.context_manifest.elder_id IS 'Context 所屬長者。';
COMMENT ON COLUMN eldercare_ai.context_manifest.tenant_id IS 'Context 所屬租戶。';
COMMENT ON COLUMN eldercare_ai.context_manifest.session_id IS '所屬對話 Session。';
COMMENT ON COLUMN eldercare_ai.context_manifest.manifest IS '實際使用的 context item ID、版本、來源與遮罩結果。';
COMMENT ON COLUMN eldercare_ai.context_manifest.item_count IS 'Context Item 數量。';
COMMENT ON COLUMN eldercare_ai.context_manifest.created_at IS '建立時間。';

CREATE TABLE eldercare_ai.transcript_version (
    transcript_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES eldercare_ai.conversation_session(session_id),
    version INTEGER NOT NULL CHECK (version > 0),
    text TEXT NOT NULL,
    language_code eldercare_ai.language_code_enum NOT NULL,
    asr_model_version VARCHAR(160) NOT NULL,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    confirmation_status VARCHAR(24) NOT NULL DEFAULT 'UNCONFIRMED' CHECK (confirmation_status IN ('UNCONFIRMED','CONFIRMED','REJECTED','CORRECTED')),
    supersedes_version_id UUID REFERENCES eldercare_ai.transcript_version(transcript_version_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_transcript_session_version UNIQUE (session_id, version)
);
COMMENT ON TABLE eldercare_ai.transcript_version IS '保存 ASR 逐字稿版本、模型、語言、信心與確認狀態。';
COMMENT ON COLUMN eldercare_ai.transcript_version.transcript_version_id IS '逐字稿版本唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.transcript_version.session_id IS '所屬對話 Session。';
COMMENT ON COLUMN eldercare_ai.transcript_version.version IS '逐字稿版本號。';
COMMENT ON COLUMN eldercare_ai.transcript_version.text IS 'ASR 最終逐字稿文字。';
COMMENT ON COLUMN eldercare_ai.transcript_version.language_code IS '逐字稿語言。';
COMMENT ON COLUMN eldercare_ai.transcript_version.asr_model_version IS 'ASR 模型版本。';
COMMENT ON COLUMN eldercare_ai.transcript_version.confidence IS '整段辨識信心，僅供系統與專業端。';
COMMENT ON COLUMN eldercare_ai.transcript_version.confirmation_status IS '長者或照護者確認狀態。';
COMMENT ON COLUMN eldercare_ai.transcript_version.supersedes_version_id IS '被此版本取代的逐字稿版本。';
COMMENT ON COLUMN eldercare_ai.transcript_version.created_at IS '版本建立時間。';

CREATE TABLE eldercare_ai.care_event (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    source_session_id UUID REFERENCES eldercare_ai.conversation_session(session_id),
    event_type VARCHAR(64) NOT NULL,
    event_time TIMESTAMPTZ,
    status VARCHAR(24) NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN ('CANDIDATE','NEEDS_REVIEW','VERIFIED','CORRECTED','REJECTED','EXCLUDED','DELETED')),
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    consent_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.care_event IS '保存飲食、活動、睡眠、用藥陳述、情緒與社交事件主紀錄。';
COMMENT ON COLUMN eldercare_ai.care_event.event_id IS '照護事件唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.care_event.elder_id IS '事件所屬長者。';
COMMENT ON COLUMN eldercare_ai.care_event.tenant_id IS '事件所屬租戶。';
COMMENT ON COLUMN eldercare_ai.care_event.source_session_id IS '來源對話 Session；人工新增可空。';
COMMENT ON COLUMN eldercare_ai.care_event.event_type IS '事件類型代碼。';
COMMENT ON COLUMN eldercare_ai.care_event.event_time IS '長者描述或人工確認的事件發生時間。';
COMMENT ON COLUMN eldercare_ai.care_event.status IS '事件生命週期狀態。';
COMMENT ON COLUMN eldercare_ai.care_event.current_version IS '目前有效版本號。';
COMMENT ON COLUMN eldercare_ai.care_event.consent_version IS '事件擷取時使用的同意版本。';
COMMENT ON COLUMN eldercare_ai.care_event.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.care_event.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.care_event_version (
    event_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES eldercare_ai.care_event(event_id),
    version INTEGER NOT NULL CHECK (version > 0),
    structured_payload JSONB NOT NULL,
    evidence_text_ref TEXT,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    supersedes_version_id UUID REFERENCES eldercare_ai.care_event_version(event_version_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_care_event_version UNIQUE (event_id, version)
);
COMMENT ON TABLE eldercare_ai.care_event_version IS '保存事件每次擷取、修正與覆核後的內容版本及證據。';
COMMENT ON COLUMN eldercare_ai.care_event_version.event_version_id IS '事件版本唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.care_event_version.event_id IS '所屬事件。';
COMMENT ON COLUMN eldercare_ai.care_event_version.version IS '事件版本號。';
COMMENT ON COLUMN eldercare_ai.care_event_version.structured_payload IS '通過 Schema 驗證的事件內容。';
COMMENT ON COLUMN eldercare_ai.care_event_version.evidence_text_ref IS '來源句或受控證據位置；避免複製不必要完整逐字稿。';
COMMENT ON COLUMN eldercare_ai.care_event_version.confidence IS '事件擷取信心。';
COMMENT ON COLUMN eldercare_ai.care_event_version.created_by_actor_id IS '建立此版本的人工或系統 Actor。';
COMMENT ON COLUMN eldercare_ai.care_event_version.supersedes_version_id IS '被此版本取代的版本。';
COMMENT ON COLUMN eldercare_ai.care_event_version.created_at IS '版本建立時間。';

CREATE TABLE eldercare_ai.review_decision (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(64) NOT NULL,
    target_id UUID NOT NULL,
    event_id UUID REFERENCES eldercare_ai.care_event(event_id),
    reviewer_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    decision eldercare_ai.review_decision_enum NOT NULL,
    reason_code VARCHAR(120),
    before_version INTEGER,
    after_version INTEGER,
    notes TEXT,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.review_decision IS '保存照護者對事件、記憶、摘要或報表的確認、修正、拒絕與排除。';
COMMENT ON COLUMN eldercare_ai.review_decision.review_id IS '覆核紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.review_decision.target_type IS '覆核目標類型。';
COMMENT ON COLUMN eldercare_ai.review_decision.target_id IS '覆核目標 ID；為多型邏輯參照。';
COMMENT ON COLUMN eldercare_ai.review_decision.event_id IS '目標為 Care Event 時的實體 FK。';
COMMENT ON COLUMN eldercare_ai.review_decision.reviewer_actor_id IS '覆核者。';
COMMENT ON COLUMN eldercare_ai.review_decision.decision IS '覆核決策。';
COMMENT ON COLUMN eldercare_ai.review_decision.reason_code IS '覆核理由碼。';
COMMENT ON COLUMN eldercare_ai.review_decision.before_version IS '覆核前版本號。';
COMMENT ON COLUMN eldercare_ai.review_decision.after_version IS '覆核後版本號。';
COMMENT ON COLUMN eldercare_ai.review_decision.notes IS '補充說明；不得保存不必要敏感內容。';
COMMENT ON COLUMN eldercare_ai.review_decision.reviewed_at IS '完成覆核時間。';
COMMENT ON COLUMN eldercare_ai.review_decision.created_at IS '紀錄建立時間。';

CREATE TABLE eldercare_ai.daily_summary (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    summary_date DATE NOT NULL,
    summary_type VARCHAR(32) NOT NULL CHECK (summary_type IN ('PROFESSIONAL_DAILY','FAMILY_DAILY','WEEKLY','MONTHLY')),
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','READY','NEEDS_REVIEW','PUBLISHED','STALE','WITHDRAWN')),
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    generated_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_summary UNIQUE (elder_id, summary_date, summary_type)
);
COMMENT ON TABLE eldercare_ai.daily_summary IS '保存長者每日、每週或每月摘要的主紀錄與目前狀態。';
COMMENT ON COLUMN eldercare_ai.daily_summary.summary_id IS '摘要唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.daily_summary.elder_id IS '摘要所屬長者。';
COMMENT ON COLUMN eldercare_ai.daily_summary.tenant_id IS '摘要所屬租戶。';
COMMENT ON COLUMN eldercare_ai.daily_summary.summary_date IS '摘要基準日期。';
COMMENT ON COLUMN eldercare_ai.daily_summary.summary_type IS '摘要類型。';
COMMENT ON COLUMN eldercare_ai.daily_summary.status IS '摘要狀態。';
COMMENT ON COLUMN eldercare_ai.daily_summary.current_version IS '目前有效版本號。';
COMMENT ON COLUMN eldercare_ai.daily_summary.generated_at IS '最近一次生成完成時間。';
COMMENT ON COLUMN eldercare_ai.daily_summary.published_at IS '發布時間。';
COMMENT ON COLUMN eldercare_ai.daily_summary.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.daily_summary.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.summary_version (
    summary_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    summary_id UUID NOT NULL REFERENCES eldercare_ai.daily_summary(summary_id),
    version INTEGER NOT NULL CHECK (version > 0),
    content JSONB NOT NULL,
    source_event_ids UUID[] NOT NULL DEFAULT '{}',
    model_version VARCHAR(160),
    prompt_version VARCHAR(80),
    safety_evaluation_id UUID REFERENCES eldercare_ai.safety_evaluation(safety_evaluation_id),
    created_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_summary_version UNIQUE (summary_id, version)
);
COMMENT ON TABLE eldercare_ai.summary_version IS '保存摘要內容版本、來源事件、模型、Prompt 與安全檢查。';
COMMENT ON COLUMN eldercare_ai.summary_version.summary_version_id IS '摘要版本唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.summary_version.summary_id IS '所屬摘要。';
COMMENT ON COLUMN eldercare_ai.summary_version.version IS '摘要版本號。';
COMMENT ON COLUMN eldercare_ai.summary_version.content IS '結構化摘要內容與未提及欄位。';
COMMENT ON COLUMN eldercare_ai.summary_version.source_event_ids IS '摘要引用的事件 ID；第一版以陣列保存邏輯參照。';
COMMENT ON COLUMN eldercare_ai.summary_version.model_version IS '生成摘要的模型版本。';
COMMENT ON COLUMN eldercare_ai.summary_version.prompt_version IS '摘要 Prompt 版本。';
COMMENT ON COLUMN eldercare_ai.summary_version.safety_evaluation_id IS '安全檢查紀錄。';
COMMENT ON COLUMN eldercare_ai.summary_version.created_by_actor_id IS '建立版本的人工或系統 Actor。';
COMMENT ON COLUMN eldercare_ai.summary_version.created_at IS '版本建立時間。';

CREATE TABLE eldercare_ai.memory (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    memory_type VARCHAR(40) NOT NULL CHECK (memory_type IN ('PREFERENCE','IMPORTANT_RELATIONSHIP','ROUTINE','COMMUNICATION_PREFERENCE','PERSONAL_HISTORY')),
    status VARCHAR(24) NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN ('CANDIDATE','CONFIRMED','ACTIVE','DEFERRED','REJECTED','INACTIVE','DELETED')),
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    confirmed_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    confirmed_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    deactivated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    consent_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.memory IS '保存候選與已確認的長期記憶主紀錄。';
COMMENT ON COLUMN eldercare_ai.memory.memory_id IS '記憶唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.memory.elder_id IS '記憶所屬長者。';
COMMENT ON COLUMN eldercare_ai.memory.tenant_id IS '記憶所屬租戶。';
COMMENT ON COLUMN eldercare_ai.memory.memory_type IS '記憶類型。';
COMMENT ON COLUMN eldercare_ai.memory.status IS '記憶狀態。';
COMMENT ON COLUMN eldercare_ai.memory.current_version IS '目前有效版本號。';
COMMENT ON COLUMN eldercare_ai.memory.confirmed_by_actor_id IS '確認此記憶的長者或授權人。';
COMMENT ON COLUMN eldercare_ai.memory.confirmed_at IS '確認時間。';
COMMENT ON COLUMN eldercare_ai.memory.activated_at IS '開始可被檢索時間。';
COMMENT ON COLUMN eldercare_ai.memory.deactivated_at IS '停用時間。';
COMMENT ON COLUMN eldercare_ai.memory.deleted_at IS '刪除時間。';
COMMENT ON COLUMN eldercare_ai.memory.consent_version IS '記憶建立或確認時使用的同意版本。';
COMMENT ON COLUMN eldercare_ai.memory.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.memory.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.memory_version (
    memory_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES eldercare_ai.memory(memory_id),
    version INTEGER NOT NULL CHECK (version > 0),
    content TEXT NOT NULL,
    source_event_ids UUID[] NOT NULL DEFAULT '{}',
    version_status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' CHECK (version_status IN ('ACTIVE','INACTIVE','DELETED')),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    created_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    supersedes_version_id UUID REFERENCES eldercare_ai.memory_version(memory_version_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_memory_version UNIQUE (memory_id, version),
    CONSTRAINT ck_memory_version_period CHECK (valid_to IS NULL OR valid_to > valid_from)
);
COMMENT ON TABLE eldercare_ai.memory_version IS '保存記憶內容、來源、有效期間與歷史版本。';
COMMENT ON COLUMN eldercare_ai.memory_version.memory_version_id IS '記憶版本唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.memory_version.memory_id IS '所屬記憶。';
COMMENT ON COLUMN eldercare_ai.memory_version.version IS '記憶版本號。';
COMMENT ON COLUMN eldercare_ai.memory_version.content IS '已正規化的記憶內容。';
COMMENT ON COLUMN eldercare_ai.memory_version.source_event_ids IS '記憶來源事件 ID；第一版以陣列保存邏輯參照。';
COMMENT ON COLUMN eldercare_ai.memory_version.version_status IS '版本是否為目前有效內容。';
COMMENT ON COLUMN eldercare_ai.memory_version.valid_from IS '版本開始有效時間。';
COMMENT ON COLUMN eldercare_ai.memory_version.valid_to IS '版本停止有效時間。';
COMMENT ON COLUMN eldercare_ai.memory_version.created_by_actor_id IS '建立此版本的人工或系統 Actor。';
COMMENT ON COLUMN eldercare_ai.memory_version.supersedes_version_id IS '被此版本取代的版本。';
COMMENT ON COLUMN eldercare_ai.memory_version.created_at IS '版本建立時間。';

CREATE TABLE eldercare_ai.outbox_event (
    outbox_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    event_type VARCHAR(160) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version > 0),
    tenant_id UUID REFERENCES eldercare_ai.tenant(tenant_id),
    elder_id UUID REFERENCES eldercare_ai.elder(elder_id),
    actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    purpose VARCHAR(64),
    consent_version INTEGER,
    trace_id VARCHAR(80) NOT NULL,
    correlation_id VARCHAR(80),
    causation_id VARCHAR(80),
    idempotency_key VARCHAR(160),
    classification eldercare_ai.data_classification_enum NOT NULL DEFAULT 'RESTRICTED',
    payload JSONB NOT NULL,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (delivery_status IN ('PENDING','PUBLISHING','PUBLISHED','FAILED')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.outbox_event IS 'Transactional Outbox；在業務交易中保存待發布 Domain Event。';
COMMENT ON COLUMN eldercare_ai.outbox_event.outbox_event_id IS 'Outbox 資料列唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.outbox_event.event_id IS '全域唯一 Domain Event ID。';
COMMENT ON COLUMN eldercare_ai.outbox_event.event_type IS '事件類型與 Major Version。';
COMMENT ON COLUMN eldercare_ai.outbox_event.aggregate_type IS '事件來源 Aggregate 類型。';
COMMENT ON COLUMN eldercare_ai.outbox_event.aggregate_id IS '事件來源 Aggregate ID。';
COMMENT ON COLUMN eldercare_ai.outbox_event.aggregate_version IS 'Aggregate 版本。';
COMMENT ON COLUMN eldercare_ai.outbox_event.tenant_id IS '事件租戶範圍。';
COMMENT ON COLUMN eldercare_ai.outbox_event.elder_id IS '事件長者範圍。';
COMMENT ON COLUMN eldercare_ai.outbox_event.actor_id IS '造成事件的 Actor。';
COMMENT ON COLUMN eldercare_ai.outbox_event.purpose IS '事件資料用途。';
COMMENT ON COLUMN eldercare_ai.outbox_event.consent_version IS '事件建立時的同意版本。';
COMMENT ON COLUMN eldercare_ai.outbox_event.trace_id IS '跨服務 Trace ID。';
COMMENT ON COLUMN eldercare_ai.outbox_event.correlation_id IS '同一工作流 Correlation ID。';
COMMENT ON COLUMN eldercare_ai.outbox_event.causation_id IS '造成此事件的 Command 或事件 ID。';
COMMENT ON COLUMN eldercare_ai.outbox_event.idempotency_key IS '事件發布與 Consumer 冪等鍵。';
COMMENT ON COLUMN eldercare_ai.outbox_event.classification IS '事件資料敏感度。';
COMMENT ON COLUMN eldercare_ai.outbox_event.payload IS '事件 Payload；不得包含完整音訊、逐字稿或 Secret。';
COMMENT ON COLUMN eldercare_ai.outbox_event.delivery_status IS '發布狀態。';
COMMENT ON COLUMN eldercare_ai.outbox_event.occurred_at IS '事件發生時間。';
COMMENT ON COLUMN eldercare_ai.outbox_event.published_at IS '成功發布時間。';
COMMENT ON COLUMN eldercare_ai.outbox_event.attempt_count IS '發布嘗試次數。';
COMMENT ON COLUMN eldercare_ai.outbox_event.last_error IS '最後一次發布錯誤。';
COMMENT ON COLUMN eldercare_ai.outbox_event.created_at IS '資料列建立時間。';
COMMENT ON COLUMN eldercare_ai.outbox_event.updated_at IS '發布技術狀態最後更新時間。';

CREATE TABLE eldercare_ai.graph_projection_record (
    projection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(64) NOT NULL,
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version > 0),
    projection_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (projection_status IN ('PENDING','SYNCED','FAILED','REMOVED')),
    graph_key VARCHAR(300),
    outbox_event_id UUID REFERENCES eldercare_ai.outbox_event(outbox_event_id),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_graph_projection UNIQUE (source_type, source_id, source_version)
);
COMMENT ON TABLE eldercare_ai.graph_projection_record IS '追蹤 Event、Memory 或 Relationship 同步至 Neptune Graph 的狀態。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.projection_id IS 'Graph 投影紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.source_type IS '投影來源類型。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.source_id IS '投影來源 ID。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.source_version IS '投影來源版本。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.projection_status IS 'Graph 投影狀態。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.graph_key IS 'Neptune Node 或 Edge 的穩定鍵。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.outbox_event_id IS '觸發投影的 Outbox Event。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.attempt_count IS '同步嘗試次數。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.last_error IS '最後一次同步錯誤。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.synced_at IS '成功同步或移除時間。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.graph_projection_record.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.care_assignment (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    care_unit_id UUID NOT NULL REFERENCES eldercare_ai.care_unit(care_unit_id),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    worker_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    service_start TIMESTAMPTZ NOT NULL,
    service_end TIMESTAMPTZ NOT NULL,
    service_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','CONFIRMED','IN_PROGRESS','COMPLETED','EXPIRED','CANCELLED','NO_SHOW')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_assignment_period CHECK (service_end > service_start)
);
COMMENT ON TABLE eldercare_ai.care_assignment IS '保存居服員或照護人員對長者的限時派案與資料作用範圍。';
COMMENT ON COLUMN eldercare_ai.care_assignment.assignment_id IS '派案唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.care_assignment.tenant_id IS '派案所屬服務機構。';
COMMENT ON COLUMN eldercare_ai.care_assignment.care_unit_id IS '派案所屬照護單位。';
COMMENT ON COLUMN eldercare_ai.care_assignment.elder_id IS '服務長者。';
COMMENT ON COLUMN eldercare_ai.care_assignment.worker_actor_id IS '被派案照護者。';
COMMENT ON COLUMN eldercare_ai.care_assignment.service_start IS '服務開始時間。';
COMMENT ON COLUMN eldercare_ai.care_assignment.service_end IS '服務結束時間。';
COMMENT ON COLUMN eldercare_ai.care_assignment.service_scope IS '可見資料範圍與可執行動作。';
COMMENT ON COLUMN eldercare_ai.care_assignment.status IS '派案狀態。';
COMMENT ON COLUMN eldercare_ai.care_assignment.version IS '樂觀鎖版本。';
COMMENT ON COLUMN eldercare_ai.care_assignment.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.care_assignment.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.service_record (
    service_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES eldercare_ai.care_assignment(assignment_id),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    worker_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    service_date DATE NOT NULL,
    record_type VARCHAR(64) NOT NULL,
    content JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','COMPLETED','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_service_record UNIQUE (assignment_id, service_date, record_type)
);
COMMENT ON TABLE eldercare_ai.service_record IS '保存有效派案期間建立的正式或草稿服務紀錄。';
COMMENT ON COLUMN eldercare_ai.service_record.service_record_id IS '服務紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.service_record.assignment_id IS '對應派案。';
COMMENT ON COLUMN eldercare_ai.service_record.elder_id IS '服務長者。';
COMMENT ON COLUMN eldercare_ai.service_record.worker_actor_id IS '執行服務的照護者。';
COMMENT ON COLUMN eldercare_ai.service_record.service_date IS '服務日期。';
COMMENT ON COLUMN eldercare_ai.service_record.record_type IS '服務紀錄類型。';
COMMENT ON COLUMN eldercare_ai.service_record.content IS '服務紀錄內容。';
COMMENT ON COLUMN eldercare_ai.service_record.status IS '服務紀錄狀態。';
COMMENT ON COLUMN eldercare_ai.service_record.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.service_record.completed_at IS '完成時間。';
COMMENT ON COLUMN eldercare_ai.service_record.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.family_relationship (
    family_relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    family_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    share_scope TEXT[] NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE','REVOKED','EXPIRED')),
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ,
    consent_id UUID NOT NULL REFERENCES eldercare_ai.consent_grant(consent_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_family_relationship_period CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT uq_family_relationship UNIQUE (elder_id, family_actor_id, consent_id)
);
COMMENT ON TABLE eldercare_ai.family_relationship IS '保存家屬與長者之間的分享關係、範圍與有效期間。';
COMMENT ON COLUMN eldercare_ai.family_relationship.family_relationship_id IS '家屬關係唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.family_relationship.elder_id IS '被分享資料的長者。';
COMMENT ON COLUMN eldercare_ai.family_relationship.family_actor_id IS '家屬 Actor。';
COMMENT ON COLUMN eldercare_ai.family_relationship.share_scope IS '可讀取的家屬資料範圍。';
COMMENT ON COLUMN eldercare_ai.family_relationship.status IS '家屬關係狀態。';
COMMENT ON COLUMN eldercare_ai.family_relationship.effective_from IS '開始生效時間。';
COMMENT ON COLUMN eldercare_ai.family_relationship.effective_to IS '停止生效時間。';
COMMENT ON COLUMN eldercare_ai.family_relationship.consent_id IS '家屬分享使用的同意紀錄。';
COMMENT ON COLUMN eldercare_ai.family_relationship.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.family_relationship.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.family_report (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    recipient_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_type eldercare_ai.report_type_enum NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','NEEDS_REVIEW','PUBLISHED','WITHDRAWN','STALE')),
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    created_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    published_at TIMESTAMPTZ,
    withdrawn_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_family_report_period CHECK (period_end >= period_start),
    CONSTRAINT uq_family_report UNIQUE (elder_id, report_type, period_start, period_end)
);
COMMENT ON TABLE eldercare_ai.family_report IS '保存家屬版日報、週報、月報或重要事件報表主紀錄。';
COMMENT ON COLUMN eldercare_ai.family_report.report_id IS '家屬報表唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.family_report.elder_id IS '報表所屬長者。';
COMMENT ON COLUMN eldercare_ai.family_report.tenant_id IS '報表所屬租戶。';
COMMENT ON COLUMN eldercare_ai.family_report.recipient_scope IS '可讀取報表的家屬關係與分享範圍快照。';
COMMENT ON COLUMN eldercare_ai.family_report.report_type IS '報表類型。';
COMMENT ON COLUMN eldercare_ai.family_report.period_start IS '報表期間開始日。';
COMMENT ON COLUMN eldercare_ai.family_report.period_end IS '報表期間結束日。';
COMMENT ON COLUMN eldercare_ai.family_report.status IS '報表狀態。';
COMMENT ON COLUMN eldercare_ai.family_report.current_version IS '目前有效版本號。';
COMMENT ON COLUMN eldercare_ai.family_report.created_by_actor_id IS '建立報表草稿的人工或系統 Actor。';
COMMENT ON COLUMN eldercare_ai.family_report.published_at IS '發布時間。';
COMMENT ON COLUMN eldercare_ai.family_report.withdrawn_at IS '撤回時間。';
COMMENT ON COLUMN eldercare_ai.family_report.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.family_report.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.report_version (
    report_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES eldercare_ai.family_report(report_id),
    version INTEGER NOT NULL CHECK (version > 0),
    content JSONB NOT NULL,
    source_summary_ids UUID[] NOT NULL DEFAULT '{}',
    source_event_ids UUID[] NOT NULL DEFAULT '{}',
    share_scope_snapshot JSONB NOT NULL,
    safety_evaluation_id UUID REFERENCES eldercare_ai.safety_evaluation(safety_evaluation_id),
    created_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_report_version UNIQUE (report_id, version)
);
COMMENT ON TABLE eldercare_ai.report_version IS '保存家屬報表內容版本、來源摘要、來源事件與分享範圍快照。';
COMMENT ON COLUMN eldercare_ai.report_version.report_version_id IS '報表版本唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.report_version.report_id IS '所屬家屬報表。';
COMMENT ON COLUMN eldercare_ai.report_version.version IS '報表版本號。';
COMMENT ON COLUMN eldercare_ai.report_version.content IS '家屬可見的結構化內容。';
COMMENT ON COLUMN eldercare_ai.report_version.source_summary_ids IS '來源摘要 ID；第一版以陣列保存邏輯參照。';
COMMENT ON COLUMN eldercare_ai.report_version.source_event_ids IS '來源事件 ID；第一版以陣列保存邏輯參照。';
COMMENT ON COLUMN eldercare_ai.report_version.share_scope_snapshot IS '建立版本時的分享範圍快照。';
COMMENT ON COLUMN eldercare_ai.report_version.safety_evaluation_id IS '發布前安全評估。';
COMMENT ON COLUMN eldercare_ai.report_version.created_by_actor_id IS '建立此版本的人工或系統 Actor。';
COMMENT ON COLUMN eldercare_ai.report_version.created_at IS '版本建立時間。';

CREATE TABLE eldercare_ai.notification_preference (
    preference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    channels eldercare_ai.notification_channel_enum[] NOT NULL DEFAULT '{}',
    frequency VARCHAR(24) NOT NULL DEFAULT 'DAILY' CHECK (frequency IN ('DAILY','WEEKLY','MONTHLY','IMPORTANT_ONLY')),
    send_time_local TIME,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Taipei',
    quiet_hours JSONB NOT NULL DEFAULT '{}'::jsonb,
    important_event_enabled BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_notification_preference UNIQUE (family_actor_id, elder_id)
);
COMMENT ON TABLE eldercare_ai.notification_preference IS '保存家屬通知通路、頻率、時段與靜默設定。';
COMMENT ON COLUMN eldercare_ai.notification_preference.preference_id IS '通知偏好唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.notification_preference.family_actor_id IS '設定通知的家屬 Actor。';
COMMENT ON COLUMN eldercare_ai.notification_preference.elder_id IS '偏好對應的長者。';
COMMENT ON COLUMN eldercare_ai.notification_preference.channels IS '啟用的通知通路。';
COMMENT ON COLUMN eldercare_ai.notification_preference.frequency IS '通知頻率。';
COMMENT ON COLUMN eldercare_ai.notification_preference.send_time_local IS '依本地時區發送的時間。';
COMMENT ON COLUMN eldercare_ai.notification_preference.timezone IS '通知時區。';
COMMENT ON COLUMN eldercare_ai.notification_preference.quiet_hours IS '靜默時段設定。';
COMMENT ON COLUMN eldercare_ai.notification_preference.important_event_enabled IS '是否啟用重要事件通知。';
COMMENT ON COLUMN eldercare_ai.notification_preference.status IS '通知偏好狀態。';
COMMENT ON COLUMN eldercare_ai.notification_preference.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.notification_preference.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.notification_delivery (
    notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES eldercare_ai.family_report(report_id),
    report_version_id UUID NOT NULL REFERENCES eldercare_ai.report_version(report_version_id),
    recipient_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    preference_id UUID REFERENCES eldercare_ai.notification_preference(preference_id),
    channel eldercare_ai.notification_channel_enum NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','SENDING','SENT','DELIVERED','OPENED','FAILED','CANCELLED')),
    scheduled_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    idempotency_key VARCHAR(160) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_notification_idempotency UNIQUE (idempotency_key)
);
COMMENT ON TABLE eldercare_ai.notification_delivery IS '保存每次家屬報表通知的排程、發送、重試、成功與失敗狀態。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.notification_id IS '通知工作唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.report_id IS '通知對應的家屬報表。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.report_version_id IS '通知引用的報表版本。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.recipient_actor_id IS '通知收件人。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.preference_id IS '發送時使用的通知偏好。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.channel IS '通知通路。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.status IS '通知狀態。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.scheduled_at IS '預定發送時間。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.sent_at IS '成功送出時間。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.opened_at IS '收件人開啟通知或連結時間。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.attempt_count IS '發送嘗試次數。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.last_error IS '最後一次發送錯誤。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.idempotency_key IS '避免同報表重複發送的冪等鍵。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.notification_delivery.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.secure_link (
    secure_link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    report_id UUID NOT NULL REFERENCES eldercare_ai.family_report(report_id),
    notification_id UUID REFERENCES eldercare_ai.notification_delivery(notification_id),
    token_hash CHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    used_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','USED','EXPIRED','REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_secure_link_token_hash UNIQUE (token_hash)
);
COMMENT ON TABLE eldercare_ai.secure_link IS '保存家屬通知中的短效安全連結、撤回、到期與使用狀態。';
COMMENT ON COLUMN eldercare_ai.secure_link.secure_link_id IS '安全連結唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.secure_link.recipient_actor_id IS '連結綁定的收件人。';
COMMENT ON COLUMN eldercare_ai.secure_link.report_id IS '連結可讀取的報表。';
COMMENT ON COLUMN eldercare_ai.secure_link.notification_id IS '產生此連結的通知。';
COMMENT ON COLUMN eldercare_ai.secure_link.token_hash IS 'Token 雜湊；不得保存原始 Token。';
COMMENT ON COLUMN eldercare_ai.secure_link.expires_at IS '連結到期時間。';
COMMENT ON COLUMN eldercare_ai.secure_link.revoked_at IS '撤回時間。';
COMMENT ON COLUMN eldercare_ai.secure_link.used_at IS '首次或一次性使用時間。';
COMMENT ON COLUMN eldercare_ai.secure_link.status IS '安全連結狀態。';
COMMENT ON COLUMN eldercare_ai.secure_link.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.secure_link.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.care_action (
    care_action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    tenant_id UUID NOT NULL REFERENCES eldercare_ai.tenant(tenant_id),
    action_type VARCHAR(40) NOT NULL CHECK (action_type IN ('CONTACT_ELDER','CONTACT_FAMILY','CONFIRM_INFORMATION','INVITE_ACTIVITY','FOLLOW_UP','OTHER')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    trigger_reason TEXT,
    related_event_ids UUID[] NOT NULL DEFAULT '{}',
    assignee_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    due_at TIMESTAMPTZ,
    priority VARCHAR(16) NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW','MEDIUM','HIGH')),
    status VARCHAR(24) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','IN_PROGRESS','COMPLETED','POSTPONED','CANCELLED')),
    resolution TEXT,
    created_by_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.care_action IS '將需要關心的事件轉成聯繫、確認、活動邀請或追蹤待辦。';
COMMENT ON COLUMN eldercare_ai.care_action.care_action_id IS '照護待辦唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.care_action.elder_id IS '待辦所屬長者。';
COMMENT ON COLUMN eldercare_ai.care_action.tenant_id IS '待辦所屬租戶。';
COMMENT ON COLUMN eldercare_ai.care_action.action_type IS '待辦類型。';
COMMENT ON COLUMN eldercare_ai.care_action.title IS '待辦標題。';
COMMENT ON COLUMN eldercare_ai.care_action.description IS '待辦說明。';
COMMENT ON COLUMN eldercare_ai.care_action.trigger_reason IS '建立待辦的原因。';
COMMENT ON COLUMN eldercare_ai.care_action.related_event_ids IS '相關事件 ID；第一版以陣列保存邏輯參照。';
COMMENT ON COLUMN eldercare_ai.care_action.assignee_actor_id IS '待辦負責人。';
COMMENT ON COLUMN eldercare_ai.care_action.due_at IS '預定完成時間。';
COMMENT ON COLUMN eldercare_ai.care_action.priority IS '優先級；不得表示醫療診斷風險。';
COMMENT ON COLUMN eldercare_ai.care_action.status IS '待辦狀態。';
COMMENT ON COLUMN eldercare_ai.care_action.resolution IS '完成、取消或排除結果。';
COMMENT ON COLUMN eldercare_ai.care_action.created_by_actor_id IS '確認並建立待辦的人員。';
COMMENT ON COLUMN eldercare_ai.care_action.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.care_action.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.proactive_trigger (
    trigger_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    consent_id UUID NOT NULL REFERENCES eldercare_ai.consent_grant(consent_id),
    source_type VARCHAR(64) NOT NULL,
    source_id UUID,
    topic_type VARCHAR(64) NOT NULL,
    status VARCHAR(28) NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN ('CANDIDATE','BLOCKED','PENDING_APPROVAL','APPROVED','SCHEDULED','READY','PLAYED','EXPIRED','CANCELLED','FAILED')),
    scheduled_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    policy_version VARCHAR(80) NOT NULL,
    blocked_reason VARCHAR(160),
    created_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    idempotency_key VARCHAR(160) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_proactive_trigger_idempotency UNIQUE (idempotency_key),
    CONSTRAINT ck_proactive_trigger_period CHECK (expires_at IS NULL OR scheduled_at IS NULL OR expires_at > scheduled_at)
);
COMMENT ON TABLE eldercare_ai.proactive_trigger IS '保存主動陪伴候選、排程、核准、阻擋、到期與播放狀態。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.trigger_id IS '主動陪伴 Trigger 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.elder_id IS 'Trigger 所屬長者。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.consent_id IS '主動陪伴獨立同意。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.source_type IS 'Trigger 來源類型。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.source_id IS 'Trigger 來源 ID。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.topic_type IS '候選互動主題類型。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.status IS 'Trigger 狀態。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.scheduled_at IS '預定互動時間。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.expires_at IS 'Trigger 失效時間。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.policy_version IS 'Eligibility 與主動陪伴 Policy 版本。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.blocked_reason IS '阻擋理由。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.created_by_actor_id IS '建立 Trigger 的照護者或系統 Actor。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.idempotency_key IS '避免同來源建立重複 Trigger 的冪等鍵。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.proactive_trigger.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.eligibility_decision (
    eligibility_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id UUID NOT NULL REFERENCES eldercare_ai.proactive_trigger(trigger_id),
    policy_id UUID NOT NULL REFERENCES eldercare_ai.policy_registry(policy_id),
    agent_run_id UUID REFERENCES eldercare_ai.agent_run(agent_run_id),
    consent_passed BOOLEAN NOT NULL,
    quiet_hours_passed BOOLEAN NOT NULL,
    frequency_passed BOOLEAN NOT NULL,
    cooldown_passed BOOLEAN NOT NULL,
    device_passed BOOLEAN NOT NULL,
    safety_passed BOOLEAN NOT NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('ALLOW','BLOCK','HUMAN_REVIEW')),
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.eligibility_decision IS '保存每次主動播放前的同意、時段、頻率、冷卻、裝置與安全判斷。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.eligibility_id IS 'Eligibility 判斷唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.trigger_id IS '被判斷的 Trigger。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.policy_id IS '使用的 Eligibility Policy。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.agent_run_id IS '若有語意分析則連結 Agent Run。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.consent_passed IS '主動陪伴同意是否有效。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.quiet_hours_passed IS '是否不在靜默時段。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.frequency_passed IS '是否未超過每日頻率上限。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.cooldown_passed IS '是否通過最短間隔。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.device_passed IS '裝置是否可互動。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.safety_passed IS '安全與敏感主題檢查是否通過。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.decision IS '最終 Eligibility 結果。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.reason_codes IS '阻擋、核准或人工覆核理由碼。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.evaluated_at IS '判斷時間。';
COMMENT ON COLUMN eldercare_ai.eligibility_decision.created_at IS '紀錄建立時間。';

CREATE TABLE eldercare_ai.follow_up_plan (
    follow_up_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    trigger_id UUID REFERENCES eldercare_ai.proactive_trigger(trigger_id),
    care_action_id UUID REFERENCES eldercare_ai.care_action(care_action_id),
    source_type VARCHAR(64),
    source_id UUID,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','COMPLETED','POSTPONED','CANCELLED','EXPIRED')),
    expires_at TIMESTAMPTZ,
    idempotency_key VARCHAR(160) NOT NULL,
    created_by_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_follow_up_idempotency UNIQUE (idempotency_key),
    CONSTRAINT ck_follow_up_period CHECK (expires_at IS NULL OR expires_at > scheduled_at)
);
COMMENT ON TABLE eldercare_ai.follow_up_plan IS '保存稍後提醒、跨日追蹤、延期、取消與完成狀態。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.follow_up_id IS '追蹤計畫唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.elder_id IS '追蹤所屬長者。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.trigger_id IS '來源主動陪伴 Trigger。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.care_action_id IS '關聯照護待辦。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.source_type IS '追蹤來源類型。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.source_id IS '追蹤來源 ID。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.scheduled_at IS '預定追蹤時間。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.status IS '追蹤狀態。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.expires_at IS '追蹤失效時間。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.idempotency_key IS '避免同來源重複追蹤的冪等鍵。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.created_by_actor_id IS '建立追蹤計畫的 Actor。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.completed_at IS '完成時間。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.follow_up_plan.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.deletion_request (
    deletion_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    requested_by_actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    consent_id UUID REFERENCES eldercare_ai.consent_grant(consent_id),
    scope TEXT[] NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'REQUESTED' CHECK (status IN ('REQUESTED','IN_PROGRESS','PARTIAL_FAILED','COMPLETED','CANCELLED')),
    reason_code VARCHAR(120),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.deletion_request IS '保存長者提出的資料刪除與衍生資料清理要求。';
COMMENT ON COLUMN eldercare_ai.deletion_request.deletion_request_id IS '刪除要求唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.deletion_request.elder_id IS '刪除資料所屬長者。';
COMMENT ON COLUMN eldercare_ai.deletion_request.requested_by_actor_id IS '提出刪除要求的人員。';
COMMENT ON COLUMN eldercare_ai.deletion_request.consent_id IS '相關同意或撤回紀錄。';
COMMENT ON COLUMN eldercare_ai.deletion_request.scope IS '要刪除的資料類型與衍生範圍。';
COMMENT ON COLUMN eldercare_ai.deletion_request.status IS '刪除流程狀態。';
COMMENT ON COLUMN eldercare_ai.deletion_request.reason_code IS '刪除原因碼。';
COMMENT ON COLUMN eldercare_ai.deletion_request.requested_at IS '提出要求時間。';
COMMENT ON COLUMN eldercare_ai.deletion_request.effective_at IS '停止新增處理的生效時間。';
COMMENT ON COLUMN eldercare_ai.deletion_request.completed_at IS '全部清理完成時間。';
COMMENT ON COLUMN eldercare_ai.deletion_request.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.deletion_request.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.deletion_job_item (
    deletion_job_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deletion_request_id UUID NOT NULL REFERENCES eldercare_ai.deletion_request(deletion_request_id),
    resource_type VARCHAR(64) NOT NULL,
    resource_id UUID,
    system_of_record VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED','SKIPPED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.deletion_job_item IS '將刪除要求拆成 Aurora、S3、Neptune、OpenSearch、Cache 等可重跑工作。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.deletion_job_item_id IS '刪除工作項目唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.deletion_request_id IS '所屬刪除要求。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.resource_type IS '待清理資源類型。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.resource_id IS '待清理資源 ID；批次型工作可空。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.system_of_record IS '目標系統，例如 AURORA、S3、NEPTUNE 或 OPENSEARCH。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.status IS '工作狀態。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.attempt_count IS '清理嘗試次數。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.last_error IS '最後一次清理錯誤。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.completed_at IS '工作完成時間。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.deletion_job_item.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.audit_record (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    tenant_id UUID REFERENCES eldercare_ai.tenant(tenant_id),
    elder_id UUID REFERENCES eldercare_ai.elder(elder_id),
    action_type VARCHAR(120) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_id UUID,
    result VARCHAR(20) NOT NULL CHECK (result IN ('SUCCESS','DENIED','FAILED')),
    reason_code VARCHAR(120),
    trace_id VARCHAR(80) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    classification eldercare_ai.data_classification_enum NOT NULL DEFAULT 'RESTRICTED'
);
COMMENT ON TABLE eldercare_ai.audit_record IS '不可變更的稽核紀錄，保存授權、查看、修改、覆核、撤回與刪除等操作。';
COMMENT ON COLUMN eldercare_ai.audit_record.audit_id IS '稽核紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.audit_record.actor_id IS '執行操作的 Actor；系統背景工作可空。';
COMMENT ON COLUMN eldercare_ai.audit_record.tenant_id IS '操作租戶範圍。';
COMMENT ON COLUMN eldercare_ai.audit_record.elder_id IS '操作長者範圍。';
COMMENT ON COLUMN eldercare_ai.audit_record.action_type IS '稽核操作類型。';
COMMENT ON COLUMN eldercare_ai.audit_record.target_type IS '被操作資源類型。';
COMMENT ON COLUMN eldercare_ai.audit_record.target_id IS '被操作資源 ID。';
COMMENT ON COLUMN eldercare_ai.audit_record.result IS '操作結果。';
COMMENT ON COLUMN eldercare_ai.audit_record.reason_code IS '拒絕或失敗理由碼。';
COMMENT ON COLUMN eldercare_ai.audit_record.trace_id IS '跨服務 Trace ID。';
COMMENT ON COLUMN eldercare_ai.audit_record.metadata IS '不含敏感原文的稽核補充資訊。';
COMMENT ON COLUMN eldercare_ai.audit_record.occurred_at IS '操作發生時間。';
COMMENT ON COLUMN eldercare_ai.audit_record.classification IS '稽核資料敏感度。';

CREATE TABLE eldercare_ai.knowledge_chunk (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_version_id UUID NOT NULL REFERENCES eldercare_ai.knowledge_source_version(source_version_id),
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    section_title VARCHAR(500),
    chunk_text TEXT NOT NULL,
    primary_category VARCHAR(120),
    region VARCHAR(120),
    service_type VARCHAR(120),
    risk_level VARCHAR(24) NOT NULL DEFAULT 'NORMAL' CHECK (risk_level IN ('NORMAL','SENSITIVE','HIGH_RISK')),
    review_status VARCHAR(24) NOT NULL DEFAULT 'NEEDS_REVIEW' CHECK (review_status IN ('NEEDS_REVIEW','REVIEWED','REJECTED','EXPIRED')),
    language_code eldercare_ai.language_code_enum NOT NULL DEFAULT 'ZH_TW',
    token_count INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_knowledge_chunk UNIQUE (source_version_id, chunk_index)
);
COMMENT ON TABLE eldercare_ai.knowledge_chunk IS '保存經解析、切片與審查的知識 Chunk 與檢索 Metadata。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.chunk_id IS 'Chunk 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.source_version_id IS 'Chunk 所屬來源版本。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.chunk_index IS '來源版本內的 Chunk 順序。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.section_title IS '章節或段落標題。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.chunk_text IS 'Chunk 完整文字；不放在管理 Sheet。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.primary_category IS '主要分類。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.region IS '適用地區。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.service_type IS '適用長照或衛教服務類型。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.risk_level IS '內容風險層級。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.review_status IS 'Chunk 審查狀態。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.language_code IS 'Chunk 主要語言。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.token_count IS '切片 Token 數。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.metadata IS '來源、適用對象、法律依據與其他檢索欄位。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.reviewed_by_actor_id IS '人工審查者。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.knowledge_chunk_embedding (
    chunk_embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES eldercare_ai.knowledge_chunk(chunk_id),
    embedding_model_version VARCHAR(200) NOT NULL,
    vector_dimension INTEGER NOT NULL CHECK (vector_dimension > 0),
    index_name VARCHAR(160) NOT NULL,
    document_id VARCHAR(200),
    embedding_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (embedding_status IN ('PENDING','INDEXED','FAILED','REMOVED')),
    embedded_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chunk_embedding UNIQUE (chunk_id, embedding_model_version)
);
COMMENT ON TABLE eldercare_ai.knowledge_chunk_embedding IS '追蹤 Chunk Embedding 模型、OpenSearch 文件位置與索引狀態。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.chunk_embedding_id IS 'Embedding 紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.chunk_id IS '被向量化的 Chunk。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.embedding_model_version IS 'Embedding 模型與版本。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.vector_dimension IS '向量維度。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.index_name IS 'OpenSearch Index 或 Collection 名稱。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.document_id IS 'OpenSearch 文件 ID。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.embedding_status IS '向量與索引狀態。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.embedded_at IS '成功向量化或索引時間。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.last_error IS '最後一次處理錯誤。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.knowledge_chunk_embedding.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.game_question (
    question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_version_id UUID REFERENCES eldercare_ai.knowledge_source_version(source_version_id),
    reviewed_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    category VARCHAR(120) NOT NULL,
    language_code eldercare_ai.language_code_enum NOT NULL,
    difficulty VARCHAR(16) NOT NULL DEFAULT 'EASY' CHECK (difficulty IN ('EASY','MEDIUM','HARD')),
    prompt_text TEXT NOT NULL,
    answer_schema JSONB NOT NULL,
    explanation TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEWED','ACTIVE','RETIRED')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.game_question IS '保存語音互動小遊戲題目、答案、來源、語言、版本與審查狀態。';
COMMENT ON COLUMN eldercare_ai.game_question.question_id IS '題目唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.game_question.source_version_id IS '衛教或文化題目的可信來源。';
COMMENT ON COLUMN eldercare_ai.game_question.reviewed_by_actor_id IS '內容審查者。';
COMMENT ON COLUMN eldercare_ai.game_question.category IS '題目分類。';
COMMENT ON COLUMN eldercare_ai.game_question.language_code IS '題目語言。';
COMMENT ON COLUMN eldercare_ai.game_question.difficulty IS '題目難度。';
COMMENT ON COLUMN eldercare_ai.game_question.prompt_text IS '題目文字。';
COMMENT ON COLUMN eldercare_ai.game_question.answer_schema IS '答案、同義答案與判定規則。';
COMMENT ON COLUMN eldercare_ai.game_question.explanation IS '答題後解釋與來源說明。';
COMMENT ON COLUMN eldercare_ai.game_question.status IS '題目狀態。';
COMMENT ON COLUMN eldercare_ai.game_question.version IS '題目版本。';
COMMENT ON COLUMN eldercare_ai.game_question.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.game_question.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.game_session (
    game_session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    conversation_session_id UUID REFERENCES eldercare_ai.conversation_session(session_id),
    status VARCHAR(20) NOT NULL DEFAULT 'STARTED' CHECK (status IN ('STARTED','COMPLETED','ABORTED','EXPIRED')),
    question_count INTEGER NOT NULL DEFAULT 0 CHECK (question_count >= 0),
    correct_count INTEGER NOT NULL DEFAULT 0 CHECK (correct_count >= 0),
    points_awarded INTEGER NOT NULL DEFAULT 0 CHECK (points_awarded >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_game_session_period CHECK (ended_at IS NULL OR ended_at >= started_at)
);
COMMENT ON TABLE eldercare_ai.game_session IS '保存長者每次語音小遊戲的開始、完成、中止與積分摘要。';
COMMENT ON COLUMN eldercare_ai.game_session.game_session_id IS '遊戲 Session 唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.game_session.elder_id IS '參與遊戲的長者。';
COMMENT ON COLUMN eldercare_ai.game_session.conversation_session_id IS '遊戲所在對話 Session。';
COMMENT ON COLUMN eldercare_ai.game_session.status IS '遊戲 Session 狀態。';
COMMENT ON COLUMN eldercare_ai.game_session.question_count IS '題目總數。';
COMMENT ON COLUMN eldercare_ai.game_session.correct_count IS '答對題數；不得用來推論健康狀態。';
COMMENT ON COLUMN eldercare_ai.game_session.points_awarded IS '本次遊戲取得積分。';
COMMENT ON COLUMN eldercare_ai.game_session.started_at IS '開始時間。';
COMMENT ON COLUMN eldercare_ai.game_session.ended_at IS '結束時間。';
COMMENT ON COLUMN eldercare_ai.game_session.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.game_session.updated_at IS '最後更新時間。';

CREATE TABLE eldercare_ai.game_answer (
    game_answer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_session_id UUID NOT NULL REFERENCES eldercare_ai.game_session(game_session_id),
    question_id UUID NOT NULL REFERENCES eldercare_ai.game_question(question_id),
    answer_text TEXT,
    asr_transcript TEXT,
    confirmation_status VARCHAR(20) NOT NULL DEFAULT 'UNCONFIRMED' CHECK (confirmation_status IN ('UNCONFIRMED','CONFIRMED','REJECTED','CORRECTED')),
    is_correct BOOLEAN,
    points_awarded INTEGER NOT NULL DEFAULT 0 CHECK (points_awarded >= 0),
    answered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_game_answer UNIQUE (game_session_id, question_id)
);
COMMENT ON TABLE eldercare_ai.game_answer IS '保存每題回答、ASR 結果、確認狀態、正確性與取得積分。';
COMMENT ON COLUMN eldercare_ai.game_answer.game_answer_id IS '答題紀錄唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.game_answer.game_session_id IS '所屬遊戲 Session。';
COMMENT ON COLUMN eldercare_ai.game_answer.question_id IS '回答的題目。';
COMMENT ON COLUMN eldercare_ai.game_answer.answer_text IS '長者確認後的答案文字。';
COMMENT ON COLUMN eldercare_ai.game_answer.asr_transcript IS 'ASR 原始辨識結果。';
COMMENT ON COLUMN eldercare_ai.game_answer.confirmation_status IS '低信心答案確認狀態。';
COMMENT ON COLUMN eldercare_ai.game_answer.is_correct IS '答案是否正確；低信心未確認時可空。';
COMMENT ON COLUMN eldercare_ai.game_answer.points_awarded IS '此題取得積分。';
COMMENT ON COLUMN eldercare_ai.game_answer.answered_at IS '回答時間。';
COMMENT ON COLUMN eldercare_ai.game_answer.created_at IS '建立時間。';

CREATE TABLE eldercare_ai.point_ledger (
    point_ledger_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    elder_id UUID NOT NULL REFERENCES eldercare_ai.elder(elder_id),
    game_session_id UUID REFERENCES eldercare_ai.game_session(game_session_id),
    game_answer_id UUID REFERENCES eldercare_ai.game_answer(game_answer_id),
    awarded_by_actor_id UUID REFERENCES eldercare_ai.actor(actor_id),
    reason_code VARCHAR(120) NOT NULL,
    points_delta INTEGER NOT NULL CHECK (points_delta <> 0),
    balance_after INTEGER CHECK (balance_after IS NULL OR balance_after >= 0),
    idempotency_key VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_point_ledger_idempotency UNIQUE (elder_id, idempotency_key)
);
COMMENT ON TABLE eldercare_ai.point_ledger IS '不可變更的積分流水帳；更正以反向調整新增紀錄，不覆蓋原紀錄。';
COMMENT ON COLUMN eldercare_ai.point_ledger.point_ledger_id IS '積分流水唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.point_ledger.elder_id IS '積分所屬長者。';
COMMENT ON COLUMN eldercare_ai.point_ledger.game_session_id IS '積分來源遊戲 Session。';
COMMENT ON COLUMN eldercare_ai.point_ledger.game_answer_id IS '積分來源答題。';
COMMENT ON COLUMN eldercare_ai.point_ledger.awarded_by_actor_id IS '人工調整積分的人員；系統自動可空。';
COMMENT ON COLUMN eldercare_ai.point_ledger.reason_code IS '積分增加或調整原因。';
COMMENT ON COLUMN eldercare_ai.point_ledger.points_delta IS '本次積分增減值。';
COMMENT ON COLUMN eldercare_ai.point_ledger.balance_after IS '記帳後餘額快照。';
COMMENT ON COLUMN eldercare_ai.point_ledger.idempotency_key IS '避免重複發放積分的冪等鍵。';
COMMENT ON COLUMN eldercare_ai.point_ledger.occurred_at IS '積分事件發生時間。';
COMMENT ON COLUMN eldercare_ai.point_ledger.created_at IS '紀錄建立時間。';

CREATE TABLE eldercare_ai.user_feedback (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID NOT NULL REFERENCES eldercare_ai.actor(actor_id),
    elder_id UUID REFERENCES eldercare_ai.elder(elder_id),
    session_id UUID REFERENCES eldercare_ai.conversation_session(session_id),
    agent_run_id UUID REFERENCES eldercare_ai.agent_run(agent_run_id),
    target_type VARCHAR(64) NOT NULL,
    target_id UUID,
    feedback_type VARCHAR(64) NOT NULL,
    rating SMALLINT CHECK (rating IS NULL OR (rating BETWEEN 1 AND 5)),
    comment TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW','REVIEWED','RESOLVED','DISMISSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE eldercare_ai.user_feedback IS '保存長者或照護者對回答、主動話題、事件、訊號與遊戲的回饋。';
COMMENT ON COLUMN eldercare_ai.user_feedback.feedback_id IS '回饋唯一識別碼。';
COMMENT ON COLUMN eldercare_ai.user_feedback.actor_id IS '提出回饋的 Actor。';
COMMENT ON COLUMN eldercare_ai.user_feedback.elder_id IS '回饋涉及的長者。';
COMMENT ON COLUMN eldercare_ai.user_feedback.session_id IS '回饋涉及的對話 Session。';
COMMENT ON COLUMN eldercare_ai.user_feedback.agent_run_id IS '回饋涉及的 Agent Run。';
COMMENT ON COLUMN eldercare_ai.user_feedback.target_type IS '回饋目標類型。';
COMMENT ON COLUMN eldercare_ai.user_feedback.target_id IS '回饋目標 ID。';
COMMENT ON COLUMN eldercare_ai.user_feedback.feedback_type IS '有幫助、沒幫助、時間不適合、不要再聊、內容重複等類型。';
COMMENT ON COLUMN eldercare_ai.user_feedback.rating IS '可選 1 至 5 分評分。';
COMMENT ON COLUMN eldercare_ai.user_feedback.comment IS '回饋文字。';
COMMENT ON COLUMN eldercare_ai.user_feedback.metadata IS '裝置、語言、原因碼等補充資料。';
COMMENT ON COLUMN eldercare_ai.user_feedback.status IS '回饋處理狀態。';
COMMENT ON COLUMN eldercare_ai.user_feedback.created_at IS '建立時間。';
COMMENT ON COLUMN eldercare_ai.user_feedback.updated_at IS '最後更新時間。';

ALTER TABLE eldercare_ai.tenant
    ADD CONSTRAINT fk_tenant_default_policy
    FOREIGN KEY (default_policy_id) REFERENCES eldercare_ai.policy_registry(policy_id);

CREATE UNIQUE INDEX uq_actor_email ON eldercare_ai.actor (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX idx_actor_status ON eldercare_ai.actor (status, actor_type);
CREATE INDEX idx_membership_actor_active ON eldercare_ai.actor_tenant_membership (actor_id, tenant_id, status);
CREATE UNIQUE INDEX uq_membership_scope ON eldercare_ai.actor_tenant_membership (actor_id, tenant_id, COALESCE(care_unit_id, '00000000-0000-0000-0000-000000000000'::uuid), role_code);
CREATE INDEX idx_elder_tenant_unit ON eldercare_ai.elder (tenant_id, primary_care_unit_id, status);
CREATE INDEX idx_relationship_elder_actor ON eldercare_ai.care_relationship (elder_id, actor_id, status, effective_from);
CREATE INDEX idx_source_review ON eldercare_ai.knowledge_source (review_status, source_kind);
CREATE INDEX idx_source_version_active ON eldercare_ai.knowledge_source_version (source_id, status, effective_date DESC);
CREATE UNIQUE INDEX uq_policy_scope ON eldercare_ai.policy_registry (COALESCE(owner_tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), policy_code, version);
CREATE INDEX idx_policy_active ON eldercare_ai.policy_registry (policy_code, status, effective_from DESC);
CREATE INDEX idx_consent_elder_purpose ON eldercare_ai.consent_grant (elder_id, purpose_code, status, effective_at DESC);
CREATE INDEX idx_session_elder_time ON eldercare_ai.conversation_session (elder_id, started_at DESC);
CREATE INDEX idx_session_state ON eldercare_ai.conversation_session (state, started_at);
CREATE INDEX idx_agent_run_trace ON eldercare_ai.agent_run (trace_id);
CREATE INDEX idx_agent_run_elder_time ON eldercare_ai.agent_run (elder_id, started_at DESC);
CREATE INDEX idx_safety_target ON eldercare_ai.safety_evaluation (target_type, target_id, evaluated_at DESC);
CREATE INDEX idx_tool_call_agent ON eldercare_ai.agent_tool_call (agent_run_id, started_at);
CREATE INDEX idx_context_agent ON eldercare_ai.context_manifest (agent_run_id);
CREATE INDEX idx_transcript_session ON eldercare_ai.transcript_version (session_id, version DESC);
CREATE INDEX idx_event_elder_time ON eldercare_ai.care_event (elder_id, event_time DESC);
CREATE INDEX idx_event_review ON eldercare_ai.care_event (tenant_id, status, created_at);
CREATE INDEX idx_event_source_session ON eldercare_ai.care_event (source_session_id);
CREATE INDEX idx_review_target ON eldercare_ai.review_decision (target_type, target_id, reviewed_at DESC);
CREATE INDEX idx_summary_elder_date ON eldercare_ai.daily_summary (elder_id, summary_date DESC, summary_type);
CREATE INDEX idx_memory_elder_status ON eldercare_ai.memory (elder_id, status, updated_at DESC);
CREATE UNIQUE INDEX uq_memory_one_active_version ON eldercare_ai.memory_version (memory_id) WHERE version_status = 'ACTIVE';
CREATE INDEX idx_outbox_pending ON eldercare_ai.outbox_event (delivery_status, created_at) WHERE delivery_status IN ('PENDING','FAILED');
CREATE INDEX idx_graph_projection_pending ON eldercare_ai.graph_projection_record (projection_status, updated_at) WHERE projection_status IN ('PENDING','FAILED');
CREATE INDEX idx_assignment_worker_time ON eldercare_ai.care_assignment (worker_actor_id, service_start, status);
CREATE INDEX idx_assignment_elder_time ON eldercare_ai.care_assignment (elder_id, service_start DESC);
CREATE INDEX idx_service_assignment ON eldercare_ai.service_record (assignment_id, service_date DESC);
CREATE INDEX idx_family_relationship_active ON eldercare_ai.family_relationship (family_actor_id, elder_id, status);
CREATE INDEX idx_family_report_elder_period ON eldercare_ai.family_report (elder_id, period_start DESC, status);
CREATE INDEX idx_notification_recipient ON eldercare_ai.notification_delivery (recipient_actor_id, status, scheduled_at);
CREATE INDEX idx_notification_report ON eldercare_ai.notification_delivery (report_id, report_version_id);
CREATE INDEX idx_secure_link_expiry ON eldercare_ai.secure_link (status, expires_at);
CREATE INDEX idx_care_action_elder_due ON eldercare_ai.care_action (elder_id, status, due_at);
CREATE INDEX idx_trigger_elder_time ON eldercare_ai.proactive_trigger (elder_id, status, scheduled_at);
CREATE INDEX idx_eligibility_trigger ON eldercare_ai.eligibility_decision (trigger_id, evaluated_at DESC);
CREATE INDEX idx_follow_up_elder ON eldercare_ai.follow_up_plan (elder_id, status, scheduled_at);
CREATE INDEX idx_deletion_request_elder ON eldercare_ai.deletion_request (elder_id, status, requested_at DESC);
CREATE UNIQUE INDEX uq_deletion_job_scope ON eldercare_ai.deletion_job_item (deletion_request_id, resource_type, COALESCE(resource_id, '00000000-0000-0000-0000-000000000000'::uuid), system_of_record);
CREATE INDEX idx_deletion_job_pending ON eldercare_ai.deletion_job_item (status, updated_at) WHERE status IN ('PENDING','FAILED');
CREATE INDEX idx_audit_elder_time ON eldercare_ai.audit_record (elder_id, occurred_at DESC);
CREATE INDEX idx_audit_actor_time ON eldercare_ai.audit_record (actor_id, occurred_at DESC);
CREATE INDEX idx_audit_trace ON eldercare_ai.audit_record (trace_id);
CREATE INDEX idx_chunk_review_category ON eldercare_ai.knowledge_chunk (review_status, primary_category, risk_level);
CREATE INDEX idx_chunk_source ON eldercare_ai.knowledge_chunk (source_version_id, chunk_index);
CREATE INDEX idx_embedding_status ON eldercare_ai.knowledge_chunk_embedding (embedding_status, updated_at);
CREATE INDEX idx_game_question_active ON eldercare_ai.game_question (status, category, language_code);
CREATE INDEX idx_game_session_elder ON eldercare_ai.game_session (elder_id, started_at DESC);
CREATE INDEX idx_point_ledger_elder ON eldercare_ai.point_ledger (elder_id, occurred_at DESC);
CREATE INDEX idx_feedback_target ON eldercare_ai.user_feedback (target_type, target_id, created_at DESC);
CREATE INDEX idx_feedback_status ON eldercare_ai.user_feedback (status, created_at);

CREATE OR REPLACE FUNCTION eldercare_ai.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION eldercare_ai.set_updated_at() IS '在 UPDATE 前自動刷新 updated_at。';

CREATE OR REPLACE FUNCTION eldercare_ai.prevent_update_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Table %.% is append-only; UPDATE/DELETE is not allowed', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END;
$$;

COMMENT ON FUNCTION eldercare_ai.prevent_update_delete() IS '保護 append-only 稽核或流水帳資料不可更新與刪除。';

CREATE OR REPLACE FUNCTION eldercare_ai.prevent_version_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Version row %.% is immutable; create a new version instead', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END;
$$;

COMMENT ON FUNCTION eldercare_ai.prevent_version_mutation() IS '保護已建立的內容版本不可覆蓋；更正時建立新版本。';

CREATE OR REPLACE FUNCTION eldercare_ai.protect_memory_version_content()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.memory_id IS DISTINCT FROM OLD.memory_id
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.content IS DISTINCT FROM OLD.content
       OR NEW.source_event_ids IS DISTINCT FROM OLD.source_event_ids
       OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
       OR NEW.created_by_actor_id IS DISTINCT FROM OLD.created_by_actor_id
       OR NEW.supersedes_version_id IS DISTINCT FROM OLD.supersedes_version_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'Memory version content is immutable; only version_status and valid_to may change';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION eldercare_ai.protect_memory_version_content() IS '允許停用舊記憶版本，但禁止覆蓋版本內容與來源。';

CREATE OR REPLACE FUNCTION eldercare_ai.protect_outbox_immutable_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.event_id IS DISTINCT FROM OLD.event_id
       OR NEW.event_type IS DISTINCT FROM OLD.event_type
       OR NEW.aggregate_type IS DISTINCT FROM OLD.aggregate_type
       OR NEW.aggregate_id IS DISTINCT FROM OLD.aggregate_id
       OR NEW.aggregate_version IS DISTINCT FROM OLD.aggregate_version
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.elder_id IS DISTINCT FROM OLD.elder_id
       OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose
       OR NEW.consent_version IS DISTINCT FROM OLD.consent_version
       OR NEW.trace_id IS DISTINCT FROM OLD.trace_id
       OR NEW.correlation_id IS DISTINCT FROM OLD.correlation_id
       OR NEW.causation_id IS DISTINCT FROM OLD.causation_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.classification IS DISTINCT FROM OLD.classification
       OR NEW.payload IS DISTINCT FROM OLD.payload
       OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
    THEN
        RAISE EXCEPTION 'Outbox event business fields are immutable after insert';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION eldercare_ai.protect_outbox_immutable_fields() IS 'Outbox 僅允許更新發布狀態、重試次數、錯誤與 published_at。';

CREATE TRIGGER trg_actor_set_updated_at
BEFORE UPDATE ON eldercare_ai.actor
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_tenant_set_updated_at
BEFORE UPDATE ON eldercare_ai.tenant
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_care_unit_set_updated_at
BEFORE UPDATE ON eldercare_ai.care_unit
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_actor_tenant_membership_set_updated_at
BEFORE UPDATE ON eldercare_ai.actor_tenant_membership
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_elder_set_updated_at
BEFORE UPDATE ON eldercare_ai.elder
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_care_relationship_set_updated_at
BEFORE UPDATE ON eldercare_ai.care_relationship
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_knowledge_source_set_updated_at
BEFORE UPDATE ON eldercare_ai.knowledge_source
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_policy_registry_set_updated_at
BEFORE UPDATE ON eldercare_ai.policy_registry
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_consent_grant_set_updated_at
BEFORE UPDATE ON eldercare_ai.consent_grant
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_conversation_session_set_updated_at
BEFORE UPDATE ON eldercare_ai.conversation_session
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_idempotency_record_set_updated_at
BEFORE UPDATE ON eldercare_ai.idempotency_record
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_care_event_set_updated_at
BEFORE UPDATE ON eldercare_ai.care_event
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_daily_summary_set_updated_at
BEFORE UPDATE ON eldercare_ai.daily_summary
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_memory_set_updated_at
BEFORE UPDATE ON eldercare_ai.memory
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_outbox_event_set_updated_at
BEFORE UPDATE ON eldercare_ai.outbox_event
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_graph_projection_record_set_updated_at
BEFORE UPDATE ON eldercare_ai.graph_projection_record
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_care_assignment_set_updated_at
BEFORE UPDATE ON eldercare_ai.care_assignment
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_service_record_set_updated_at
BEFORE UPDATE ON eldercare_ai.service_record
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_family_relationship_set_updated_at
BEFORE UPDATE ON eldercare_ai.family_relationship
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_family_report_set_updated_at
BEFORE UPDATE ON eldercare_ai.family_report
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_notification_preference_set_updated_at
BEFORE UPDATE ON eldercare_ai.notification_preference
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_notification_delivery_set_updated_at
BEFORE UPDATE ON eldercare_ai.notification_delivery
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_secure_link_set_updated_at
BEFORE UPDATE ON eldercare_ai.secure_link
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_care_action_set_updated_at
BEFORE UPDATE ON eldercare_ai.care_action
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_proactive_trigger_set_updated_at
BEFORE UPDATE ON eldercare_ai.proactive_trigger
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_follow_up_plan_set_updated_at
BEFORE UPDATE ON eldercare_ai.follow_up_plan
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_deletion_request_set_updated_at
BEFORE UPDATE ON eldercare_ai.deletion_request
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_deletion_job_item_set_updated_at
BEFORE UPDATE ON eldercare_ai.deletion_job_item
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_knowledge_chunk_set_updated_at
BEFORE UPDATE ON eldercare_ai.knowledge_chunk
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_knowledge_chunk_embedding_set_updated_at
BEFORE UPDATE ON eldercare_ai.knowledge_chunk_embedding
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_game_question_set_updated_at
BEFORE UPDATE ON eldercare_ai.game_question
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_game_session_set_updated_at
BEFORE UPDATE ON eldercare_ai.game_session
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_user_feedback_set_updated_at
BEFORE UPDATE ON eldercare_ai.user_feedback
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.set_updated_at();

CREATE TRIGGER trg_audit_record_append_only
BEFORE UPDATE OR DELETE ON eldercare_ai.audit_record
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.prevent_update_delete();

CREATE TRIGGER trg_point_ledger_append_only
BEFORE UPDATE OR DELETE ON eldercare_ai.point_ledger
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.prevent_update_delete();

CREATE TRIGGER trg_care_event_version_immutable
BEFORE UPDATE OR DELETE ON eldercare_ai.care_event_version
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.prevent_version_mutation();

CREATE TRIGGER trg_summary_version_immutable
BEFORE UPDATE OR DELETE ON eldercare_ai.summary_version
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.prevent_version_mutation();

CREATE TRIGGER trg_memory_version_protect_content
BEFORE UPDATE ON eldercare_ai.memory_version
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.protect_memory_version_content();

CREATE TRIGGER trg_memory_version_no_delete
BEFORE DELETE ON eldercare_ai.memory_version
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.prevent_version_mutation();

CREATE TRIGGER trg_report_version_immutable
BEFORE UPDATE OR DELETE ON eldercare_ai.report_version
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.prevent_version_mutation();

CREATE TRIGGER trg_outbox_event_protect_business_fields
BEFORE UPDATE ON eldercare_ai.outbox_event
FOR EACH ROW
EXECUTE FUNCTION eldercare_ai.protect_outbox_immutable_fields();

COMMENT ON SCHEMA eldercare_ai IS '智慧長照 AI 陪伴系統核心資料庫 Schema；Aurora PostgreSQL 為交易事實來源，Graph/Search 為可重建投影。';

COMMIT;
