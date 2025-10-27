import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  Svg: React.ComponentType<React.ComponentProps<'svg'>>;
  description: ReactNode;
};

/** Ícones inline com currentColor para herdar as cores do tema */
const CatalogIcon = (props: React.ComponentProps<'svg'>) => (
  <svg viewBox="0 0 48 48" aria-hidden="true" {...props}>
    <rect x="6" y="6" width="14" height="14" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
    <rect x="28" y="6" width="14" height="14" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
    <rect x="6" y="28" width="14" height="14" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
    <rect x="28" y="28" width="14" height="14" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
  </svg>
);

const AutomationIcon = (props: React.ComponentProps<'svg'>) => (
  <svg viewBox="0 0 48 48" aria-hidden="true" {...props}>
    <circle cx="24" cy="24" r="8" fill="none" stroke="currentColor" strokeWidth="2"/>
    <path d="M24 6v6M24 36v6M6 24h6M36 24h6M12 12l4 4M32 32l4 4M12 36l4-4M32 16l4-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </svg>
);

const SecurityIcon = (props: React.ComponentProps<'svg'>) => (
  <svg viewBox="0 0 48 48" aria-hidden="true" {...props}>
    <path d="M24 4l16 6v10c0 9.94-6.12 18.9-16 22-9.88-3.1-16-12.06-16-22V10l16-6z" fill="none" stroke="currentColor" strokeWidth="2"/>
    <path d="M16 24l5 5 11-11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const FeatureList: FeatureItem[] = [
  {
    title: 'Catálogo modular',
    Svg: CatalogIcon,
    description: (
      <>
        Blocos por categoria com navegação simples, RBAC <em>ANY-of</em> e UI por iframe.
        O host lê <code>/catalog/dev</code> e monta a experiência automaticamente.
      </>
    ),
  },
  {
    title: 'Automações padronizadas',
    Svg: AutomationIcon,
    description: (
      <>
        Padrão de endpoints: <code>/schema</code>, <code>/ui</code>, <code>/submit</code> e consultas de
        <code> submissions</code>. Validação Pydantic v2, filas via <em>BackgroundTasks</em> e auditoria.
      </>
    ),
  },
  {
    title: 'Governança & segurança',
    Svg: SecurityIcon,
    description: (
      <>
        CORS restrito, cookies de sessão, erros claros (400–422) e logs com contexto.
        Sem segredos no repositório. Contraste e legibilidade alinhados à identidade AGEPAR.
      </>
    ),
  },
];

function Feature({title, Svg, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4', styles.item)}>
      <div className={styles.iconWrap} aria-hidden="true">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className={styles.textWrap}>
        <Heading as="h3" className={styles.title}>{title}</Heading>
        <p className={styles.desc}>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={clsx('row', styles.rowGap)}>
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
