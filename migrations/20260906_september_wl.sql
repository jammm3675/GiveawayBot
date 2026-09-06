begin;

alter table public.users
    add column if not exists ethereum_wallet text,
    add column if not exists ethereum_wallet_updated_at timestamptz,
    add column if not exists september_wl_nft_count integer,
    add column if not exists september_wl_count integer,
    add column if not exists september_wl_checked_at timestamptz,
    add column if not exists september_wl_checked_wallet text;

alter table public.users
    drop constraint if exists users_ethereum_wallet_check,
    add constraint users_ethereum_wallet_check
        check (ethereum_wallet is null or ethereum_wallet ~* '^0x[0-9a-f]{40}$'),
    drop constraint if exists users_september_wl_nft_count_check,
    add constraint users_september_wl_nft_count_check
        check (september_wl_nft_count is null or september_wl_nft_count >= 0),
    drop constraint if exists users_september_wl_count_check,
    add constraint users_september_wl_count_check
        check (september_wl_count is null or september_wl_count >= 0);

comment on column public.users.ethereum_wallet is
    'Temporary September WL campaign: user-provided OpenSea mint wallet.';
comment on column public.users.september_wl_nft_count is
    'Temporary September WL campaign: cached NOTAPES count from Getgems.';
comment on column public.users.september_wl_count is
    'Temporary September WL campaign: floor(september_wl_nft_count / 4).';
comment on column public.users.september_wl_checked_at is
    'Temporary September WL campaign: timestamp of the last successful Getgems check.';
comment on column public.users.september_wl_checked_wallet is
    'Temporary September WL campaign: TON wallet address associated with the cached count.';

commit;
