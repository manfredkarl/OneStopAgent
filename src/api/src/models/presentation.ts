export type SlideType = 'title' | 'executive-summary' | 'use-case' | 'architecture' | 'services' | 'cost' | 'business-value' | 'next-steps';

export interface SlideDefinition {
  type: SlideType;
  title: string;
  content: Record<string, unknown>;
  required: boolean;
  sourceAgent?: string;
}

export interface DeckStructure {
  slides: SlideDefinition[];
  metadata: DeckMetadata;
}

export interface DeckMetadata {
  slideCount: number;
  fileSize?: number;
  generatedAt: Date;
  sourceHash: string;
  missingSections: string[];
}

export interface ExportResponse {
  buffer: Buffer;
  filename: string;
  contentType: string;
  metadata: DeckMetadata;
}
