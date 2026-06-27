/** Per-repository document subtypes — mirror of the backend subtype enums. */

export const FinancialSubtype = {
  AnnualReport: 'annual_report',
  FinancialStatement: 'financial_statement',
  InvestmentReport: 'investment_report',
  RegulatoryFiling: 'regulatory_filing',
  TermSheet: 'term_sheet',
  Research: 'research',
  Prospectus: 'prospectus',
  CreditMemo: 'credit_memo',
  UserUpload: 'user_upload',
} as const;
export type FinancialSubtype = (typeof FinancialSubtype)[keyof typeof FinancialSubtype];

export const ProposalSubtype = {
  PastProposal: 'past_proposal',
  CaseStudy: 'case_study',
  StatementOfWork: 'statement_of_work',
  Pitch: 'pitch',
  Methodology: 'methodology',
} as const;
export type ProposalSubtype = (typeof ProposalSubtype)[keyof typeof ProposalSubtype];

export const TemplateSubtype = {
  ExecutiveSummary: 'executive_summary',
  ProposalStructure: 'proposal_structure',
  Pricing: 'pricing',
  Timeline: 'timeline',
  RiskAssessment: 'risk_assessment',
} as const;
export type TemplateSubtype = (typeof TemplateSubtype)[keyof typeof TemplateSubtype];
