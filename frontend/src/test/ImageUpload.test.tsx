import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImageUpload } from '@/components/ImageUpload';

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

describe('ImageUpload', () => {
  it('renders the file picker and the configured size limit', () => {
    render(<ImageUpload onUpload={vi.fn()} maxSizeMb={250} />);

    expect(screen.getByRole('button', { name: /choose a file/i })).toBeInTheDocument();
    expect(screen.getByText(/up to 250 MB/i)).toBeInTheDocument();
  });

  it('rejects a file over the configured size limit with that number', () => {
    const onUpload = vi.fn();
    render(<ImageUpload onUpload={onUpload} maxSizeMb={10} />);
    const big = new File([new Uint8Array(11 * 1024 * 1024)], 'huge.fits');

    fireEvent.change(fileInput(), { target: { files: [big] } });

    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/larger than the 10 MB limit/i)).toBeInTheDocument();
  });

  it('shows an indeterminate status while the server prepares the image', () => {
    render(<ImageUpload onUpload={vi.fn()} isLoading progress={null} />);

    expect(screen.getByRole('status')).toHaveTextContent(/preparing/i);
    expect(screen.queryByRole('button', { name: /choose a file/i })).not.toBeInTheDocument();
  });

  it('shows a percentage while the file transfers', () => {
    render(<ImageUpload onUpload={vi.fn()} isLoading progress={0.42} />);

    expect(screen.getByRole('status')).toHaveTextContent('42%');
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
