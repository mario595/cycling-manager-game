import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createReport } from '../api'
import { ReportProblemButton } from './ReportProblem'

vi.mock('../api', () => ({ createReport: vi.fn() }))

const mockCreateReport = vi.mocked(createReport)

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ReportProblemButton />
    </MemoryRouter>,
  )
}

function openForm() {
  fireEvent.click(screen.getByRole('button', { name: 'Report a problem' }))
}

function typeText(value: string) {
  fireEvent.change(screen.getByRole('textbox'), { target: { value } })
}

beforeEach(() => {
  mockCreateReport.mockReset()
})

describe('ReportProblemButton', () => {
  it('opens the form over the current screen', () => {
    renderAt('/finances')

    expect(screen.queryByRole('dialog')).toBeNull()
    openForm()

    expect(screen.getByRole('dialog', { name: 'Report a problem' })).toBeInTheDocument()
  })

  it('sends the category, the trimmed text and the screen it was opened on', async () => {
    mockCreateReport.mockResolvedValue({} as never)
    renderAt('/race/7?tab=results')
    openForm()

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'balance' } })
    typeText('  Climbers win everything.  ')
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(mockCreateReport).toHaveBeenCalledWith('balance', 'Climbers win everything.', '/race/7?tab=results')
    expect(screen.getByRole('status')).toHaveTextContent('Report received')
  })

  it('keeps the text and shows why when sending fails', async () => {
    mockCreateReport.mockRejectedValue(new Error('You have sent 20 reports in the last 24 hours.'))
    renderAt('/roster')
    openForm()

    typeText('Rider list is empty.')
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('20 reports in the last 24 hours')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('Rider list is empty.')
  })

  it('will not send blank text', () => {
    renderAt('/roster')
    openForm()

    typeText('   ')

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('closes on cancel without sending', () => {
    renderAt('/roster')
    openForm()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(mockCreateReport).not.toHaveBeenCalled()
  })
})
