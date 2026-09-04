import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImageUpload } from '@/components/ImageUpload';

describe('ImageUpload', () => {
  it('renders the file picker and accepted formats hint', () => {
    render(<ImageUpload onUpload={vi.fn()} />);

    expect(screen.getByRole('button', { name: /choose a file/i })).toBeInTheDocument();
    expect(screen.getByText(/up to 100 MB/i)).toBeInTheDocument();
  });

  it('shows a loading label while uploading', () => {
    render(<ImageUpload onUpload={vi.fn()} isLoading />);

    expect(screen.getByRole('button', { name: /uploading/i })).toBeDisabled();
  });
});
