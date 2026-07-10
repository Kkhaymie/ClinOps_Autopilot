// frontend/src/app/letters/page.tsx
'use client'
import { useState } from 'react'
import { PageLayout } from '@/components/PageLayout'
import { Mail, Upload, CheckCircle } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function LettersPage() {
  const [patientCode, setPatientCode] = useState('')
  const [language, setLanguage]       = useState('English')
  const [file, setFile]               = useState<File | null>(null)
  const [uploading, setUploading]     = useState(false)
  const [done, setDone]               = useState(false)
  const [error, setError]             = useState('')

  async function handleUpload() {
    if (!file || !patientCode) {
      setError('Please select a file and enter a patient code.')
      return
    }
    setUploading(true)
    setError('')
    try {
      // Upload image to Cloudinary via backend
      const formData = new FormData()
      formData.append('file', file)
      formData.append('patient_code', patientCode)
      formData.append('language', language)

       const res = await fetch(`${API}/api/upload-letter`, {
         method: 'POST',
         body: formData,
       })
       if (!res.ok) throw new Error('Upload failed')
       setDone(true)
     } catch (e: any) {
       setError(e.message || 'Upload failed. Please try again.')
     } finally {
       setUploading(false)
     }
}

if (done) {
  return (
    <PageLayout
      title="Physical Letters"
      subtitle="Upload and process handwritten patient letters"
    >
      <div className="max-w-md text-center py-16 mx-auto">
        <CheckCircle
          size={64}
          className="text-green-500 mx-auto mb-4"
        />
        <h2 className="text-xl font-semibold text-gray-900 mb-2">
           Letter Submitted
        </h2>
        <p className="text-gray-500 text-sm mb-6">
           The letter is being processed by ClinOps Autopilot.
           It will appear in the Pending Approvals queue within
           60 seconds.
        </p>
        <button
          onClick={() => {
             setDone(false)
             setFile(null)
             setPatientCode('')
           }}
          className="bg-[#0A0F2C] text-white px-6 py-2.5
                      rounded-lg text-sm font-medium"
        >
           Upload Another Letter
        </button>
      </div>
    </PageLayout>
  )
}

return (
  <PageLayout
    title="Physical Letters"
    subtitle="Photograph and upload handwritten letters from patients"
  >
    <div className="max-w-lg">
<div className="bg-white rounded-xl border border-gray-100
                shadow-sm p-6 space-y-5">

 <div className="flex items-center gap-3 pb-4
                 border-b border-gray-100">
   <Mail size={24} className="text-[#F5C518]" />
   <div>
     <p className="font-semibold text-gray-900">
       Letter Intake Portal
     </p>
     <p className="text-xs text-gray-500">
       For reception staff — total time under 90 seconds
     </p>
   </div>
 </div>

 {/* Patient code */}
 <div>
   <label className="block text-sm font-medium
                     text-gray-700 mb-1.5">
     Patient Code *
   </label>
   <input
     type="text"
     placeholder="e.g. PT-NG-0001"
     className="w-full border border-gray-200 rounded-lg
                px-3 py-2.5 text-sm focus:outline-none
                focus:ring-2 focus:ring-blue-200"
     value={patientCode}
     onChange={e => setPatientCode(e.target.value.toUpperCase())}
   />
 </div>

 {/* Language */}
 <div>
   <label className="block text-sm font-medium
                     text-gray-700 mb-1.5">
     Letter Language *
   </label>
   <select
     className="w-full border border-gray-200 rounded-lg
                px-3 py-2.5 text-sm focus:outline-none
                focus:ring-2 focus:ring-blue-200"
      value={language}
      onChange={e => setLanguage(e.target.value)}
  >
    {[
      'English','Yoruba','Igbo','Hausa',
      'Hausa (Ajami script)','Arabic',
      'Hindi','Chinese','French','Other'
    ].map(l => (
      <option key={l} value={l}>{l}</option>
    ))}
  </select>
</div>

{/* File upload */}
<div>
  <label className="block text-sm font-medium
                    text-gray-700 mb-1.5">
    Letter Photo or Scan *
  </label>
  <label className="flex flex-col items-center justify-center
                    border-2 border-dashed border-gray-200
                    rounded-xl py-8 px-4 cursor-pointer
                    hover:border-blue-300 hover:bg-blue-50
                    transition-colors">
    <Upload size={28} className="text-gray-300 mb-2" />
    <p className="text-sm text-gray-500">
      {file
        ? file.name
        : 'Click to select photo or scan'}
    </p>
    <p className="text-xs text-gray-400 mt-1">
      JPG, PNG or PDF — both sides if needed
    </p>
    <input
      type="file"
      accept="image/*,application/pdf"
      className="hidden"
      onChange={e => setFile(e.target.files?.[0] || null)}
    />
  </label>
</div>

{error && (
                  <p className="text-sm text-red-600 bg-red-50
                                border border-red-200 rounded-lg px-3 py-2">
                    {error}
                  </p>
             )}

             <button
               onClick={handleUpload}
               disabled={uploading || !file || !patientCode}
               className="w-full bg-[#0A0F2C] hover:bg-[#152045]
                          text-white font-semibold py-3 rounded-lg
                          text-sm transition-colors
                          disabled:opacity-40 disabled:cursor-not-allowed
                          flex items-center justify-center gap-2"
             >
               <Upload size={16} />
               {uploading ? 'Processing...' : 'Submit for Processing'}
             </button>

              <p className="text-xs text-gray-400 text-center">
                The AI will transcribe, translate, classify, and route
                this letter automatically. No further action needed.
              </p>
            </div>
          </div>
        </PageLayout>
    )
}
