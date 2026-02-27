import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Module mock must be declared before any imports of the module
vi.mock('@/api/chargers', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/chargers')>();
  return {
    ...actual,
    useInjectStatus: vi.fn(),
  };
});

import { InjectStatusPanel, VALID_TRANSITIONS, FAULTED_ERROR_CODES } from './InjectStatusPanel';
import { useInjectStatus } from '@/api/chargers';
import type { ChargerDetailResponse } from '@/types/ocpp';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCharger(evseState = 'Available'): ChargerDetailResponse {
  return {
    id: 'CP-1',
    charge_point_id: 'CP-1',
    connection_url: 'ws://test',
    charger_name: 'Test Charger',
    ocpp_version: '1.6',
    location_id: 'loc-1',
    evse_count: 1,
    connected: true,
    power_type: 'DC',
    ocpp_status: evseState,
    evses: [
      {
        evse_id: 1,
        state: evseState,
        transaction_id: null,
        meter: { energy_Wh: 0, power_W: 0, voltage_V: 0, current_A: 0 },
      },
    ],
    config: {},
  };
}

function renderPanel(evseState = 'Available') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <InjectStatusPanel chargePointId="CP-1" charger={makeCharger(evseState)} />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(useInjectStatus).mockReturnValue({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    isIdle: true,
    reset: vi.fn(),
    variables: undefined,
    data: undefined,
    error: null,
    failureCount: 0,
    failureReason: null,
    status: 'idle',
    submittedAt: 0,
    context: undefined,
  } as ReturnType<typeof useInjectStatus>);
});

// ---------------------------------------------------------------------------
// Exported constants
// ---------------------------------------------------------------------------

describe('VALID_TRANSITIONS constant', () => {
  it('covers all 8 EVSE states', () => {
    const states = ['Available', 'Preparing', 'Charging', 'SuspendedEV', 'SuspendedEVSE', 'Finishing', 'Faulted', 'Unavailable'];
    for (const s of states) {
      expect(VALID_TRANSITIONS[s]).toBeDefined();
    }
  });

  it('Available → Preparing and Unavailable only', () => {
    expect(VALID_TRANSITIONS['Available']).toEqual(expect.arrayContaining(['Preparing', 'Unavailable']));
    expect(VALID_TRANSITIONS['Available']).not.toContain('Charging');
    expect(VALID_TRANSITIONS['Available']).not.toContain('Faulted');
  });

  it('Preparing → Charging, Available, Faulted, Unavailable', () => {
    expect(VALID_TRANSITIONS['Preparing']).toEqual(
      expect.arrayContaining(['Charging', 'Available', 'Faulted', 'Unavailable'])
    );
  });

  it('Faulted → Available, Unavailable only', () => {
    expect(VALID_TRANSITIONS['Faulted']).toEqual(expect.arrayContaining(['Available', 'Unavailable']));
    expect(VALID_TRANSITIONS['Faulted']).not.toContain('Charging');
    expect(VALID_TRANSITIONS['Faulted']).not.toContain('Faulted');
  });
});

describe('FAULTED_ERROR_CODES constant', () => {
  it('contains 15 error codes (NoError excluded)', () => {
    expect(FAULTED_ERROR_CODES).toHaveLength(15);
  });

  it('does not include NoError', () => {
    expect(FAULTED_ERROR_CODES).not.toContain('NoError');
  });

  it('includes expected codes', () => {
    expect(FAULTED_ERROR_CODES).toContain('InternalError');
    expect(FAULTED_ERROR_CODES).toContain('GroundFailure');
    expect(FAULTED_ERROR_CODES).toContain('WeakSignal');
  });
});

// ---------------------------------------------------------------------------
// Component rendering
// ---------------------------------------------------------------------------

describe('InjectStatusPanel rendering', () => {
  it('renders the Inject Status heading', () => {
    renderPanel();
    // Heading text lives in a <span>; the submit button also contains "Inject Status",
    // so target the span specifically to avoid multiple-element match.
    expect(screen.getByText('Inject Status', { selector: 'span' })).toBeInTheDocument();
  });

  it('renders the EVSE label', () => {
    renderPanel();
    expect(screen.getByText('EVSE')).toBeInTheDocument();
  });

  it('renders the New Status label', () => {
    renderPanel();
    expect(screen.getByText('New Status')).toBeInTheDocument();
  });

  it('renders Inject Status submit button', () => {
    renderPanel();
    expect(screen.getByTestId('inject-status-submit')).toBeInTheDocument();
  });

  it('submit button is disabled when no status selected (initial state)', () => {
    renderPanel();
    expect(screen.getByTestId('inject-status-submit')).toBeDisabled();
  });

  it('does not render error_code, info, or vendor fields for non-Faulted state', () => {
    renderPanel('Available');
    expect(screen.queryByText(/error code/i)).toBeNull();
    expect(screen.queryByPlaceholderText(/diagnostic info/i)).toBeNull();
    expect(screen.queryByPlaceholderText(/e\.g\. e42/i)).toBeNull();
  });

  it('is open by default (content visible without clicking trigger)', () => {
    renderPanel();
    // If collapsed, "New Status" label would not be visible
    expect(screen.getByText('New Status')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Mutation call on submit
// ---------------------------------------------------------------------------

describe('InjectStatusPanel submit behaviour', () => {
  it('calls useInjectStatus with chargePointId', () => {
    renderPanel();
    // useInjectStatus hook should be called with the chargePointId
    expect(vi.mocked(useInjectStatus)).toHaveBeenCalledWith('CP-1');
  });

  it('does not call mutate when submit button is clicked with no status selected', () => {
    const mutate = vi.fn();
    vi.mocked(useInjectStatus).mockReturnValue({ mutate, isPending: false } as ReturnType<typeof useInjectStatus>);
    renderPanel();
    fireEvent.click(screen.getByTestId('inject-status-submit'));
    expect(mutate).not.toHaveBeenCalled();
  });
});
