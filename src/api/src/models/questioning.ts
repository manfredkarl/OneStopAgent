export interface GuidedQuestion {
  questionId: string;
  questionText: string;
  category: QuestionCategory;
  defaultValue?: string;
  required: boolean;
  order: number;
}

export type QuestionCategory = 'users' | 'scale' | 'geography' | 'compliance' | 'integration' | 'timeline' | 'value';

export interface QuestionAnswer {
  questionId: string;
  answer: string;
  isDefault: boolean;
  isAssumed: boolean;
}

export interface QuestioningState {
  questions: GuidedQuestion[];
  answers: QuestionAnswer[];
  currentIndex: number;
  completed: boolean;
}
