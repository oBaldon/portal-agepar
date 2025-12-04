import type { ReactNode } from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import styles from './index.module.css';
import HomepageFeatures from '../components/HomepageFeatures';

function Hero() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <header className={styles.hero}>
      <div className={`container ${styles.heroInner}`}>
        <div className={styles.heroLeft}>
          <h1 className={styles.title}>Plataforma AGEPAR — Dev Docs</h1>
          <p className={styles.subtitle}>
            BFF (FastAPI), Host (React/Vite/TS), Catálogo modular, Automações e Docs — tudo no mesmo monorepo.
          </p>

          <div className={styles.ctaRow}>
            <Link className={`button button--primary ${styles.cta}`} to="/docs/intro">
              🚀 Começar pela Introdução
            </Link>

            <Link
              className={`button button--accent ${styles.cta}`}
              to="/docs/visão-geral-e-arquitetura"
            >
              🧭 Visão Geral & Arquitetura
            </Link>

            {/* CTA para a aplicação em si */}
            <a
              className={`button button--secondary ${styles.cta}`}
              href="/"
              target="_blank"
              rel="noopener noreferrer"
            >
              🌐 Abrir Portal (App)
            </a>
          </div>

          <div className={styles.meta}>
            <span>Dev stack:</span>
            <ul>
              <li>Host: Vite + React/TypeScript</li>
              <li>BFF: FastAPI (Pydantic v2, PostgreSQL)</li>
              <li>Docs: Docusaurus + Mermaid</li>
            </ul>
          </div>
        </div>

        <div className={styles.heroRight}>
          <div className={styles.codeCard}>
            <div className={styles.codeHeader}>docker compose (dev)</div>
            <pre className={styles.codeBlock}>
{`services:
  postgres:
    image: postgres:16
    ports: ["5432:5432"]

  bff:
    build: ./apps/bff
    ports: ["8000:8000"]
    depends_on: ["postgres"]

  host:
    build: ./apps/host
    ports: ["5173:5173"]

  docs:
    build: ./apps/docs-site`}
            </pre>
            <div className={styles.codeFooter}>
              <code>docker compose -f infra/docker-compose.dev.yml up --build</code>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function FeatureGrid() {
  const cards = [
    {
      title: 'Frontend (Host)',
      desc: 'Navbar por categorias, leitura do catálogo e RBAC simples.',
      to: '/docs/frontend-host-react-vite-ts',
    },
    {
      title: 'BFF (FastAPI)',
      desc: 'Rotas /api, validação Pydantic v2, normalização e erros claros.',
      to: '/docs/bff-fastapi',
    },
    {
      title: 'Automações',
      desc: 'Módulos isolados com UI via iframe e endpoints padrão.',
      to: '/docs/automations-padrão-de-módulos',
    },
    {
      title: 'Catálogo',
      desc: 'Estrutura JSON, categories/blocks e convenções.',
      to: '/docs/catálogo-catalog-dev',
    },
    {
      title: 'Segurança',
      desc: 'CORS restrito, cookies de sessão e superfícies públicas.',
      to: '/docs/segurança',
    },
    {
      title: 'Observabilidade',
      desc: 'Padrões de log, contexto em exceptions e métricas.',
      to: '/docs/observabilidade',
    },
    {
      title: 'Testes',
      desc: 'cURL/pytest, Vitest e roteiros manuais.',
      to: '/docs/testes',
    },
    {
      title: 'Documentação (Docusaurus)',
      desc: 'Estrutura das docs, snippets e diagramas.',
      to: '/docs/documentação-docusaurus',
    },
    {
      title: 'Guias de Produto',
      desc: 'Fluxo de compras público e mapeamento para automations.',
      to: '/docs/guias-de-produto-fluxo-compras-público',
    },
    {
      title: 'Apêndices',
      desc: 'Tipos TS, Pydantic, JSON Schema, convenções e roadmap.',
      to: '/docs/apêndices',
    },
  ];

  return (
    <section className="container margin-vert--lg">
      <div className={styles.grid}>
        {cards.map((c) => (
          <Link key={c.title} to={c.to} className={styles.card}>
            <h3>{c.title}</h3>
            <p>{c.desc}</p>
            <span className={styles.cardLink}>Abrir seção →</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const { siteConfig } = useDocusaurusContext();

  return (
    <Layout
      title={siteConfig.title ?? 'Plataforma AGEPAR — Dev Docs'}
      description="Documentação técnica da Plataforma AGEPAR (BFF, Host, Catálogo, Automações e Fluxo de Compras Público)."
    >
      <Hero />
      <HomepageFeatures />
      <FeatureGrid />
    </Layout>
  );
}
