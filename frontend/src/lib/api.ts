export type ClientErrorKind =
  | 'no_data'
  | 'not_found'
  | 'http'
  | 'network'
  | 'timeout'
  | 'invalid_response';

export class ClientError extends Error {
  readonly kind: ClientErrorKind;
  readonly status: number | null;
  readonly code: string | null;

  constructor(kind: ClientErrorKind, message: string, status: number | null = null, code: string | null = null) {
    super(message);
    this.name = 'ClientError';
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function safeParseJson(text: string): { value: unknown } | null {
  if (!text) return null;
  try {
    return { value: JSON.parse(text) };
  } catch {
    return null;
  }
}

function errorFromResponse(status: number, body: unknown): ClientError {
  if (
    body !== null
    && typeof body === 'object'
    && 'error' in body
    && body.error !== null
    && typeof body.error === 'object'
    && 'code' in body.error
    && typeof body.error.code === 'string'
  ) {
    const code = body.error.code;
    if (status === 503 && code === 'dataset_unavailable') {
      return new ClientError('no_data', 'Исходные данные недоступны', status, code);
    }
    if (status === 404 && code === 'house_not_found') {
      return new ClientError('not_found', 'Дом отсутствует в пилотной выборке', status, code);
    }
    return new ClientError('http', `API вернул ошибку ${status}`, status, code);
  }

  if (status === 503) {
    return new ClientError('no_data', 'Исходные данные недоступны', status, null);
  }
  if (status === 404) {
    return new ClientError('not_found', 'Дом отсутствует в пилотной выборке', status, null);
  }
  return new ClientError('http', `API вернул ошибку ${status}`, status, null);
}

export async function requestJson<T>(
  path: string,
  validate: (value: unknown) => T,
  externalSignal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new DOMException('Timeout', 'AbortError')), 12_000);

  const abortExternal = () => controller.abort(new DOMException('Aborted', 'AbortError'));
  if (externalSignal?.aborted) {
    abortExternal();
  } else {
    externalSignal?.addEventListener('abort', abortExternal, { once: true });
  }

  try {
    const response = await fetch(path, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });

    const bodyText = await response.text();
    const body = safeParseJson(bodyText)?.value;

    if (!response.ok) {
      throw errorFromResponse(response.status, body);
    }
    if (body === null || body === undefined) {
      throw new ClientError('invalid_response', 'API вернул пустой ответ');
    }

    try {
      return validate(body);
    } catch (error) {
      throw new ClientError(
        'invalid_response',
        error instanceof Error ? error.message : 'Некорректный формат ответа API',
      );
    }
  } catch (error) {
    if (isAbortError(error)) {
      if (externalSignal?.aborted) throw error;
      throw new ClientError('timeout', 'Превышено время ожидания ответа сервера');
    }
    if (error instanceof ClientError) throw error;
    throw new ClientError('network', 'Не удалось связаться с сервером');
  } finally {
    clearTimeout(timeout);
    externalSignal?.removeEventListener('abort', abortExternal);
  }
}
