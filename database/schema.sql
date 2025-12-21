-- ============================================
-- FinanceGPT - Database Schema for Supabase
-- ============================================
-- Run this in Supabase SQL Editor (supabase.com/dashboard/project/YOUR_PROJECT/sql)
-- ============================================

-- Enable UUID extension (usually already enabled in Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. USERS TABLE
-- ============================================
-- Extends Supabase auth.users with app-specific data
-- Password is handled by Supabase Auth automatically!

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Users can only see/edit their own data
CREATE POLICY "Users can view own data" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own data" ON users
    FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can insert own data" ON users
    FOR INSERT WITH CHECK (auth.uid() = id);


-- ============================================
-- 2. USER_PROFILES TABLE (Financial Profile)
-- ============================================
-- Stores financial information for personalized analysis

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Income Information
    monthly_income DECIMAL(12,2),                    -- Ingreso mensual
    income_currency TEXT DEFAULT 'MXN',              -- Moneda (MXN, USD, EUR, etc.)
    income_frequency TEXT DEFAULT 'monthly',         -- monthly, biweekly, weekly
    additional_income DECIMAL(12,2) DEFAULT 0,       -- Ingresos adicionales

    -- Financial Goals
    savings_goal_percentage DECIMAL(5,2) DEFAULT 20, -- % del ingreso a ahorrar
    emergency_fund_months INTEGER DEFAULT 6,         -- Meses de fondo de emergencia

    -- Preferences
    preferred_language TEXT DEFAULT 'es',            -- Idioma preferido
    notification_enabled BOOLEAN DEFAULT TRUE,
    risk_tolerance TEXT DEFAULT 'moderate',          -- conservative, moderate, aggressive

    -- Metadata
    onboarding_completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id)
);

-- Enable Row Level Security
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile" ON user_profiles
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own profile" ON user_profiles
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own profile" ON user_profiles
    FOR INSERT WITH CHECK (auth.uid() = user_id);


-- ============================================
-- 3. CATEGORIES TABLE
-- ============================================
-- Predefined and custom transaction categories

CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,  -- NULL = system category
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    icon TEXT,                                            -- Emoji or icon name
    color TEXT,                                           -- Hex color code
    parent_id UUID REFERENCES categories(id),             -- For subcategories
    is_system BOOLEAN DEFAULT FALSE,                      -- System vs user-created
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;

-- Users can see system categories and their own
CREATE POLICY "Users can view categories" ON categories
    FOR SELECT USING (is_system = TRUE OR auth.uid() = user_id);

CREATE POLICY "Users can insert own categories" ON categories
    FOR INSERT WITH CHECK (auth.uid() = user_id AND is_system = FALSE);

CREATE POLICY "Users can update own categories" ON categories
    FOR UPDATE USING (auth.uid() = user_id AND is_system = FALSE);

CREATE POLICY "Users can delete own categories" ON categories
    FOR DELETE USING (auth.uid() = user_id AND is_system = FALSE);


-- ============================================
-- 4. TRANSACTIONS TABLE
-- ============================================
-- All financial transactions (income and expenses)

CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Transaction Details
    amount DECIMAL(12,2) NOT NULL,
    currency TEXT DEFAULT 'MXN',
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    description TEXT NOT NULL,

    -- Categorization (by AI agent)
    category_id UUID REFERENCES categories(id),
    subcategory TEXT,

    -- AI Analysis
    ai_category_confidence DECIMAL(3,2),              -- 0.00 to 1.00
    ai_insights TEXT,                                  -- AI-generated insights

    -- Temporal
    transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Source
    source TEXT DEFAULT 'manual',                      -- manual, import, recurring
    external_id TEXT,                                  -- ID from bank import

    -- Metadata
    tags TEXT[],                                       -- User-defined tags
    notes TEXT,
    is_recurring BOOLEAN DEFAULT FALSE,
    recurring_id UUID,                                 -- Link to recurring transaction

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_transactions_user_date ON transactions(user_id, transaction_date DESC);
CREATE INDEX idx_transactions_category ON transactions(category_id);
CREATE INDEX idx_transactions_type ON transactions(user_id, type);

-- Enable Row Level Security
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own transactions" ON transactions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own transactions" ON transactions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own transactions" ON transactions
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own transactions" ON transactions
    FOR DELETE USING (auth.uid() = user_id);


-- ============================================
-- 5. BUDGETS TABLE
-- ============================================
-- Monthly budgets by category

CREATE TABLE IF NOT EXISTS budgets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id UUID REFERENCES categories(id),

    -- Budget Details
    name TEXT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency TEXT DEFAULT 'MXN',

    -- Period
    period_type TEXT DEFAULT 'monthly' CHECK (period_type IN ('weekly', 'monthly', 'yearly')),
    start_date DATE NOT NULL,
    end_date DATE,                                     -- NULL = ongoing

    -- Alerts
    alert_threshold DECIMAL(5,2) DEFAULT 80,          -- Alert at 80% spent
    alert_enabled BOOLEAN DEFAULT TRUE,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE budgets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own budgets" ON budgets
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own budgets" ON budgets
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own budgets" ON budgets
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own budgets" ON budgets
    FOR DELETE USING (auth.uid() = user_id);


-- ============================================
-- 6. GOALS TABLE
-- ============================================
-- Financial goals (savings, debt payoff, etc.)

CREATE TABLE IF NOT EXISTS goals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Goal Details
    name TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('savings', 'debt_payoff', 'investment', 'purchase', 'emergency_fund', 'other')),

    -- Amounts
    target_amount DECIMAL(12,2) NOT NULL,
    current_amount DECIMAL(12,2) DEFAULT 0,
    currency TEXT DEFAULT 'MXN',

    -- Timeline
    target_date DATE,
    monthly_contribution DECIMAL(12,2),               -- Suggested by AI

    -- Status
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
    priority INTEGER DEFAULT 1,                        -- 1 = highest priority

    -- AI Recommendations
    ai_strategy TEXT,                                  -- AI-generated saving strategy
    ai_progress_analysis TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own goals" ON goals
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own goals" ON goals
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own goals" ON goals
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own goals" ON goals
    FOR DELETE USING (auth.uid() = user_id);


-- ============================================
-- 7. CONVERSATIONS TABLE
-- ============================================
-- Chat conversations with the AI assistant

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Conversation Details
    title TEXT,                                        -- Auto-generated from first message
    summary TEXT,                                      -- AI-generated summary

    -- Agent Path
    complexity TEXT DEFAULT 'simple' CHECK (complexity IN ('simple', 'complex')),
    agents_used TEXT[],                                -- ['categorizer', 'planner', 'executor']

    -- Status
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived')),

    -- Metadata
    message_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for listing user conversations
CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);

-- Enable Row Level Security
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own conversations" ON conversations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own conversations" ON conversations
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own conversations" ON conversations
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own conversations" ON conversations
    FOR DELETE USING (auth.uid() = user_id);


-- ============================================
-- 8. MESSAGES TABLE
-- ============================================
-- Individual messages in conversations

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Message Content
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,

    -- AI Metadata
    agent_name TEXT,                                   -- Which agent responded
    model_used TEXT,                                   -- e.g., 'llama-3.3-70b'
    tokens_used INTEGER,

    -- Tool Usage
    tool_calls JSONB,                                  -- Tools called by agent
    tool_results JSONB,                                -- Results from tools

    -- Feedback
    user_rating INTEGER CHECK (user_rating >= 1 AND user_rating <= 5),
    user_feedback TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fetching conversation messages
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- Enable Row Level Security
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own messages" ON messages
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own messages" ON messages
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own messages" ON messages
    FOR UPDATE USING (auth.uid() = user_id);


-- ============================================
-- 9. RECURRING_TRANSACTIONS TABLE
-- ============================================
-- Templates for recurring transactions

CREATE TABLE IF NOT EXISTS recurring_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Transaction Template
    amount DECIMAL(12,2) NOT NULL,
    currency TEXT DEFAULT 'MXN',
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    description TEXT NOT NULL,
    category_id UUID REFERENCES categories(id),

    -- Recurrence
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'yearly')),
    day_of_month INTEGER,                              -- For monthly (1-31)
    day_of_week INTEGER,                               -- For weekly (0-6, 0=Sunday)

    -- Period
    start_date DATE NOT NULL,
    end_date DATE,                                     -- NULL = indefinite
    next_occurrence DATE,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE recurring_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own recurring" ON recurring_transactions
    FOR ALL USING (auth.uid() = user_id);


-- ============================================
-- 10. TAGS TABLE (User-defined flexible labels)
-- ============================================
-- Allows users to create custom tags like: "vacaciones", "estudios", "emergencia"

CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Tag Details
    name TEXT NOT NULL,
    color TEXT DEFAULT '#6366F1',                      -- Hex color
    icon TEXT,                                          -- Emoji

    -- Usage Stats (updated by trigger)
    usage_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique tag name per user
    UNIQUE(user_id, name)
);

-- Enable Row Level Security
ALTER TABLE tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own tags" ON tags
    FOR ALL USING (auth.uid() = user_id);

-- Index for quick lookup
CREATE INDEX idx_tags_user ON tags(user_id);


-- ============================================
-- 11. TRANSACTION_TAGS (Many-to-Many)
-- ============================================
-- Links transactions to multiple tags

CREATE TABLE IF NOT EXISTS transaction_tags (
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (transaction_id, tag_id)
);

-- Enable Row Level Security
ALTER TABLE transaction_tags ENABLE ROW LEVEL SECURITY;

-- Users can only manage their own transaction tags
CREATE POLICY "Users can manage own transaction_tags" ON transaction_tags
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM transactions t
            WHERE t.id = transaction_id AND t.user_id = auth.uid()
        )
    );


-- ============================================
-- 12. CUSTOM_FIELDS (Dynamic user-defined fields)
-- ============================================
-- Allows users to define their own tracking fields

CREATE TABLE IF NOT EXISTS custom_fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Field Definition
    name TEXT NOT NULL,                                -- e.g., "Proyecto", "Cliente", "Prioridad"
    field_type TEXT NOT NULL CHECK (field_type IN ('text', 'number', 'boolean', 'date', 'select')),
    description TEXT,

    -- For 'select' type: available options
    options JSONB,                                     -- ["Opción 1", "Opción 2", "Opción 3"]

    -- Where this field applies
    applies_to TEXT NOT NULL CHECK (applies_to IN ('transaction', 'goal', 'budget', 'all')),

    -- Metadata
    is_required BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, name)
);

-- Enable Row Level Security
ALTER TABLE custom_fields ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own custom_fields" ON custom_fields
    FOR ALL USING (auth.uid() = user_id);


-- ============================================
-- 13. CUSTOM_FIELD_VALUES (Values for custom fields)
-- ============================================
-- Stores actual values for user-defined fields

CREATE TABLE IF NOT EXISTS custom_field_values (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    custom_field_id UUID NOT NULL REFERENCES custom_fields(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Reference to entity (one of these will be set)
    transaction_id UUID REFERENCES transactions(id) ON DELETE CASCADE,
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE,
    budget_id UUID REFERENCES budgets(id) ON DELETE CASCADE,

    -- The actual value (stored as text, parsed based on field_type)
    value TEXT NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE custom_field_values ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own field_values" ON custom_field_values
    FOR ALL USING (auth.uid() = user_id);

-- Index for quick lookup by entity
CREATE INDEX idx_custom_field_values_transaction ON custom_field_values(transaction_id);
CREATE INDEX idx_custom_field_values_goal ON custom_field_values(goal_id);
CREATE INDEX idx_custom_field_values_budget ON custom_field_values(budget_id);


-- ============================================
-- 14. CARD_TEMPLATES (Predefined card templates)
-- ============================================
-- System-provided templates that users can activate

CREATE TABLE IF NOT EXISTS card_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Template Info
    name TEXT NOT NULL,                                -- "Control de Gastos Universitarios"
    description TEXT,                                  -- "Ideal para estudiantes..."
    icon TEXT,                                         -- Emoji
    color TEXT,                                        -- Hex color

    -- Template Category
    template_type TEXT NOT NULL CHECK (template_type IN (
        'expense_tracker',      -- Seguimiento de gastos
        'income_tracker',       -- Seguimiento de ingresos
        'budget',               -- Presupuesto
        'savings_goal',         -- Meta de ahorro
        'debt_tracker',         -- Seguimiento de deudas
        'investment',           -- Inversiones
        'project',              -- Proyecto específico
        'custom'                -- Personalizado
    )),

    -- Default fields for this template (JSON array)
    -- Each field: {name, type, required, options?, description?}
    default_fields JSONB NOT NULL,

    -- Metadata
    is_system BOOLEAN DEFAULT TRUE,                    -- System vs user-created template
    is_popular BOOLEAN DEFAULT FALSE,                  -- Show in "Popular" section
    display_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- No RLS needed - templates are public (read-only for users)


-- ============================================
-- 15. USER_CARDS (User's active cards)
-- ============================================
-- Cards that a user has activated/created

CREATE TABLE IF NOT EXISTS user_cards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Card Info (can override template values)
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    color TEXT DEFAULT '#6366F1',

    -- Template reference (NULL if custom card)
    template_id UUID REFERENCES card_templates(id),

    -- Card type (inherited from template or set manually)
    card_type TEXT NOT NULL CHECK (card_type IN (
        'expense_tracker',
        'income_tracker',
        'budget',
        'savings_goal',
        'debt_tracker',
        'investment',
        'project',
        'custom'
    )),

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_pinned BOOLEAN DEFAULT FALSE,                   -- Show at top
    display_order INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE user_cards ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own cards" ON user_cards
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_user_cards_user ON user_cards(user_id, is_active, display_order);


-- ============================================
-- 16. CARD_FIELDS (Fields in a user's card)
-- ============================================
-- Custom fields for each user card

CREATE TABLE IF NOT EXISTS card_fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    card_id UUID NOT NULL REFERENCES user_cards(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Field Definition
    name TEXT NOT NULL,
    field_type TEXT NOT NULL CHECK (field_type IN ('text', 'number', 'currency', 'boolean', 'date', 'select', 'tags')),
    description TEXT,

    -- For 'select' type
    options JSONB,                                     -- ["Opción 1", "Opción 2"]

    -- Validation
    is_required BOOLEAN DEFAULT FALSE,
    default_value TEXT,

    -- Display
    display_order INTEGER DEFAULT 0,
    is_visible BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE card_fields ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own card_fields" ON card_fields
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_card_fields_card ON card_fields(card_id, display_order);


-- ============================================
-- 17. CARD_ENTRIES (Data entries in a card)
-- ============================================
-- Actual data stored in each card

CREATE TABLE IF NOT EXISTS card_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    card_id UUID NOT NULL REFERENCES user_cards(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Entry data (JSON object with field values)
    -- Example: {"monto": 500, "descripcion": "Libros", "fecha": "2024-01-15"}
    data JSONB NOT NULL,

    -- Optional: link to transaction (for expense/income trackers)
    transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,

    -- Metadata
    entry_date DATE DEFAULT CURRENT_DATE,
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE card_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own card_entries" ON card_entries
    FOR ALL USING (auth.uid() = user_id);

CREATE INDEX idx_card_entries_card ON card_entries(card_id, entry_date DESC);
CREATE INDEX idx_card_entries_user ON card_entries(user_id, created_at DESC);


-- ============================================
-- 18. INSERT DEFAULT CARD TEMPLATES
-- ============================================

INSERT INTO card_templates (name, description, icon, color, template_type, default_fields, is_popular, display_order) VALUES
    -- Expense Trackers
    (
        'Gastos Universitarios',
        'Controla tus gastos de estudios: libros, materiales, transporte al campus',
        '🎓',
        '#6366F1',
        'expense_tracker',
        '[
            {"name": "Monto", "type": "currency", "required": true},
            {"name": "Descripción", "type": "text", "required": true},
            {"name": "Categoría", "type": "select", "options": ["Libros", "Materiales", "Transporte", "Comida campus", "Copias", "Software", "Otro"]},
            {"name": "Materia", "type": "text"},
            {"name": "Fecha", "type": "date", "required": true}
        ]'::jsonb,
        TRUE,
        1
    ),
    (
        'Gastos de Vacaciones',
        'Planifica y registra todos los gastos de tu viaje',
        '✈️',
        '#EC4899',
        'expense_tracker',
        '[
            {"name": "Monto", "type": "currency", "required": true},
            {"name": "Descripción", "type": "text", "required": true},
            {"name": "Categoría", "type": "select", "options": ["Transporte", "Hospedaje", "Comida", "Actividades", "Souvenirs", "Otro"]},
            {"name": "Lugar", "type": "text"},
            {"name": "Fecha", "type": "date", "required": true}
        ]'::jsonb,
        TRUE,
        2
    ),
    (
        'Gastos Fijos Mensuales',
        'Registra tus gastos recurrentes: renta, servicios, suscripciones',
        '📅',
        '#F59E0B',
        'expense_tracker',
        '[
            {"name": "Monto", "type": "currency", "required": true},
            {"name": "Concepto", "type": "text", "required": true},
            {"name": "Tipo", "type": "select", "options": ["Renta", "Luz", "Agua", "Gas", "Internet", "Teléfono", "Streaming", "Gym", "Seguro", "Otro"]},
            {"name": "Día de pago", "type": "number"},
            {"name": "Es automático", "type": "boolean"}
        ]'::jsonb,
        TRUE,
        3
    ),
    (
        'Control de Deudas',
        'Gestiona tus préstamos y tarjetas de crédito',
        '💳',
        '#EF4444',
        'debt_tracker',
        '[
            {"name": "Nombre deuda", "type": "text", "required": true},
            {"name": "Monto total", "type": "currency", "required": true},
            {"name": "Monto pagado", "type": "currency"},
            {"name": "Tasa interés", "type": "number"},
            {"name": "Pago mensual", "type": "currency"},
            {"name": "Fecha límite", "type": "date"}
        ]'::jsonb,
        TRUE,
        4
    ),
    (
        'Meta de Ahorro',
        'Define y trackea tu progreso hacia una meta de ahorro',
        '🎯',
        '#22C55E',
        'savings_goal',
        '[
            {"name": "Meta", "type": "text", "required": true},
            {"name": "Monto objetivo", "type": "currency", "required": true},
            {"name": "Ahorro actual", "type": "currency"},
            {"name": "Ahorro mensual", "type": "currency"},
            {"name": "Fecha objetivo", "type": "date"},
            {"name": "Prioridad", "type": "select", "options": ["Alta", "Media", "Baja"]}
        ]'::jsonb,
        TRUE,
        5
    ),
    (
        'Ingresos Freelance',
        'Registra tus ingresos por proyectos independientes',
        '💻',
        '#10B981',
        'income_tracker',
        '[
            {"name": "Monto", "type": "currency", "required": true},
            {"name": "Cliente", "type": "text", "required": true},
            {"name": "Proyecto", "type": "text"},
            {"name": "Estado", "type": "select", "options": ["Pendiente", "Facturado", "Pagado"]},
            {"name": "Fecha", "type": "date", "required": true}
        ]'::jsonb,
        FALSE,
        6
    ),
    (
        'Gastos de Mascota',
        'Controla los gastos de tu compañero peludo',
        '🐕',
        '#8B5CF6',
        'expense_tracker',
        '[
            {"name": "Monto", "type": "currency", "required": true},
            {"name": "Concepto", "type": "text", "required": true},
            {"name": "Categoría", "type": "select", "options": ["Comida", "Veterinario", "Medicinas", "Accesorios", "Estética", "Otro"]},
            {"name": "Mascota", "type": "text"},
            {"name": "Fecha", "type": "date", "required": true}
        ]'::jsonb,
        FALSE,
        7
    ),
    (
        'Presupuesto de Proyecto',
        'Gestiona el presupuesto de un proyecto específico',
        '📊',
        '#0EA5E9',
        'project',
        '[
            {"name": "Nombre proyecto", "type": "text", "required": true},
            {"name": "Presupuesto total", "type": "currency", "required": true},
            {"name": "Gastado", "type": "currency"},
            {"name": "Categoría gasto", "type": "text"},
            {"name": "Estado", "type": "select", "options": ["En progreso", "Pausado", "Completado"]},
            {"name": "Notas", "type": "text"}
        ]'::jsonb,
        FALSE,
        8
    )
ON CONFLICT DO NOTHING;


-- ============================================
-- 19. INSERT DEFAULT CATEGORIES
-- ============================================

INSERT INTO categories (name, type, icon, color, is_system) VALUES
    -- Income Categories
    ('Salario', 'income', '💰', '#22C55E', TRUE),
    ('Freelance', 'income', '💻', '#10B981', TRUE),
    ('Inversiones', 'income', '📈', '#059669', TRUE),
    ('Otros Ingresos', 'income', '💵', '#047857', TRUE),

    -- Expense Categories
    ('Alimentación', 'expense', '🍔', '#EF4444', TRUE),
    ('Transporte', 'expense', '🚗', '#F97316', TRUE),
    ('Vivienda', 'expense', '🏠', '#F59E0B', TRUE),
    ('Servicios', 'expense', '💡', '#EAB308', TRUE),
    ('Salud', 'expense', '🏥', '#84CC16', TRUE),
    ('Entretenimiento', 'expense', '🎬', '#22C55E', TRUE),
    ('Ropa', 'expense', '👕', '#14B8A6', TRUE),
    ('Educación', 'expense', '📚', '#06B6D4', TRUE),
    ('Suscripciones', 'expense', '📱', '#0EA5E9', TRUE),
    ('Restaurantes', 'expense', '🍽️', '#3B82F6', TRUE),
    ('Compras', 'expense', '🛒', '#6366F1', TRUE),
    ('Mascotas', 'expense', '🐕', '#8B5CF6', TRUE),
    ('Regalos', 'expense', '🎁', '#A855F7', TRUE),
    ('Viajes', 'expense', '✈️', '#D946EF', TRUE),
    ('Otros Gastos', 'expense', '📦', '#EC4899', TRUE)
ON CONFLICT DO NOTHING;


-- ============================================
-- 11. HELPER FUNCTIONS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to all tables with updated_at
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_transactions_updated_at
    BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_budgets_updated_at
    BEFORE UPDATE ON budgets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_goals_updated_at
    BEFORE UPDATE ON goals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_recurring_transactions_updated_at
    BEFORE UPDATE ON recurring_transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- 12. FUNCTION TO CREATE USER PROFILE ON SIGNUP
-- ============================================

-- Automatically create user and profile when someone signs up
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    -- Insert into users table
    INSERT INTO public.users (id, email, full_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name'),
        NEW.raw_user_meta_data->>'avatar_url'
    );

    -- Create empty profile
    INSERT INTO public.user_profiles (user_id)
    VALUES (NEW.id);

    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- Trigger on auth.users
CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();


-- ============================================
-- SUCCESS MESSAGE
-- ============================================
-- If you see this, all tables were created successfully!
--
-- Tables created:
-- 1. users - User accounts (linked to Supabase Auth)
-- 2. user_profiles - Financial profile (income, preferences)
-- 3. categories - Transaction categories (system + custom)
-- 4. transactions - All financial transactions
-- 5. budgets - Monthly/periodic budgets
-- 6. goals - Financial goals (savings, debt, etc.)
-- 7. conversations - Chat sessions with AI
-- 8. messages - Individual chat messages
-- 9. recurring_transactions - Recurring transaction templates
-- 10. tags - User-defined labels (vacaciones, estudios, emergencia)
-- 11. transaction_tags - Many-to-many: transactions <-> tags
-- 12. custom_fields - User-defined dynamic fields
-- 13. custom_field_values - Values for custom fields
-- 14. card_templates - Predefined card templates (8 templates)
-- 15. user_cards - User's active cards
-- 16. card_fields - Custom fields for each card
-- 17. card_entries - Data entries in cards
--
-- Features included:
-- - Row Level Security (RLS) on all tables
-- - Automatic updated_at timestamps
-- - Auto-creation of user profile on signup
-- - 19 default expense/income categories
-- - DYNAMIC SYSTEM: Users can create custom tags and fields!
-- ============================================
