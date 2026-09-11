const base64UrlToUint8Array = (value: string): Uint8Array => {
  const pad = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + pad).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from(raw, c => c.charCodeAt(0));
};

const arrayBufferToBase64Url = (value: ArrayBuffer): string => {
  const bytes = new Uint8Array(value);
  let raw = '';
  bytes.forEach((b) => { raw += String.fromCharCode(b); });
  return btoa(raw).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

export const parseRegistrationOptions = (optionsJson: string): PublicKeyCredentialCreationOptions => {
  const options = JSON.parse(optionsJson);
  return {
    ...options,
    challenge: base64UrlToUint8Array(options.challenge),
    user: {
      ...options.user,
      id: base64UrlToUint8Array(options.user.id),
    },
    excludeCredentials: (options.excludeCredentials || []).map((c: any) => ({
      ...c,
      id: base64UrlToUint8Array(c.id),
    })),
  };
};

export const parseAuthenticationOptions = (optionsJson: string): PublicKeyCredentialRequestOptions => {
  const options = JSON.parse(optionsJson);
  return {
    ...options,
    challenge: base64UrlToUint8Array(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((c: any) => ({
      ...c,
      id: base64UrlToUint8Array(c.id),
    })),
  };
};

export const credentialToJSON = (credential: PublicKeyCredential) => {
  const response: any = credential.response;
  return {
    id: credential.id,
    rawId: arrayBufferToBase64Url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: arrayBufferToBase64Url(response.clientDataJSON),
      attestationObject: response.attestationObject ? arrayBufferToBase64Url(response.attestationObject) : undefined,
      authenticatorData: response.authenticatorData ? arrayBufferToBase64Url(response.authenticatorData) : undefined,
      signature: response.signature ? arrayBufferToBase64Url(response.signature) : undefined,
      userHandle: response.userHandle ? arrayBufferToBase64Url(response.userHandle) : undefined,
    },
    clientExtensionResults: credential.getClientExtensionResults?.() || {},
  };
};
