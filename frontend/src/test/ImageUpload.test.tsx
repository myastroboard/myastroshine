import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImageUpload } from '@/components/ImageUpload';

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

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

  it.each(['frame.fits', 'photo.CR2', 'photo.nef', 'stack.tif'])(
    'accepts a %s upload',
    (name) => {
      const onUpload = vi.fn();
      render(<ImageUpload onUpload={onUpload} />);
      const file = new File(['data'], name, { type: 'application/octet-stream' });

      fireEvent.change(fileInput(), { target: { files: [file] } });

      expect(onUpload).toHaveBeenCalledWith(file);
    },
  );

  it('rejects an unsupported extension', () => {
    const onUpload = vi.fn();
    render(<ImageUpload onUpload={onUpload} />);
    const file = new File(['data'], 'photo.bmp', { type: 'image/bmp' });

    fireEvent.change(fileInput(), { target: { files: [file] } });

    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/not supported/i)).toBeInTheDocument();
  });
});
