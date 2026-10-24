<script setup lang="ts">
  import { onMounted, ref } from 'vue'

  // interfaces
  interface InferenceImage {
    guid: string
    name: string
    filepath: string
    upload_group_id: string
    uploaded_at?: string
  }

  interface Detection {
    id: number
    confidence: number
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  // variables
  const images = ref<InferenceImage[]>([])
  const expandedImages = ref<Record<string, boolean>>({})
  const imageDetails = ref<Record<string, string[]>>({})

  // track active detections and selected task ID per image
  const activeDetections = ref<Record<string, Detection[]>>({})
  const activeTaskId = ref<Record<string, string>>({})

  // track image natrual vs display dimensions for correct box scaling
  const imageDimensions = ref<Record<string, { naturalWidth: number; naturalHeight: number; displayWidth: number; displayHeight: number }>>({})

  // fetch existing uploaded images, to be called on mount TODO -paginate
  const fetchImages = async () => {
    try {
      const response = await fetch('/images')
      if (response.ok) {
        images.value = await response.json()
      }
    } catch (err) {
      console.error('Failed to fetch images:', err)
    }
  }

  // start a task for the image guid
  const startTaskOnImage = async(image_guid: string) => {
    
    try {
      const response = await fetch(`/process-image/${image_guid}`, { method: 'POST' });
      if (!response.ok) {
  throw new Error(`Server returned status ${response.status}`);
}
    } catch (err) {
      console.error('Failed to start processing on image:', err)
    }
  }

  // fetch contents for an expanded image
  const toggleExpand = async (img: InferenceImage) => {

    // strict boolean (if never opened image, then undefined. !undefined = true, !!undefined = false)
    const currentState = !!expandedImages.value[img.guid]
    expandedImages.value[img.guid] = !currentState

    // If opening and we haven't fetched the tasks for this image yet, fetch them
    if (!currentState && !imageDetails.value[img.guid]) {
      try {
        const response = await fetch(`/images/${img.guid}/tasks`)
        if (response.ok) {
          const data = await response.json()
          imageDetails.value[img.guid] = data.tasks || []
        } else {
          imageDetails.value[img.guid] = []
        }
      } catch (err) {
        console.error('Failed to fetch tasks for image', err)
        imageDetails.value[img.guid] = []
      }
    }
  }

  // record image dimensions when loaded
  const onImageLoad = (event: Event, imgGuid: string) => {
    const imgEl = event.target as HTMLImageElement
    imageDimensions.value[imgGuid] = {
      naturalWidth: imgEl.naturalWidth,
      naturalHeight: imgEl.naturalHeight,
      displayWidth: imgEl.clientWidth,
      displayHeight: imgEl.clientHeight
    }
  }

  // fetch task details and detections for a clicked task
  const fetchTaskDetections = async(imgGuid: string, taskId: string) => {
    try {
      activeTaskId.value[imgGuid] = taskId
      const response = await fetch(`/task-details/${taskId}`)
      if(response.ok) {
        const data = await response.json()
        activeDetections.value[imgGuid] = data.detections || []
      } else {
        activeDetections.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch task detections:', err)
      activeDetections.value[imgGuid] = []
    }
  }

  // calculate proportional bounding box style
  const calculateBoxStyle = (det: Detection, imgGuid: string) => {
    const dims = imageDimensions.value[imgGuid]
    if(!dims || dims.naturalWidth === 0) return {}

    const scaleX = dims.displayWidth / dims.naturalWidth
    const scaleY = dims.displayHeight / dims.naturalHeight

    return {
      left: `${det.x_min * scaleX}px`,
      top: `${det.y_min * scaleY}px`,
      width: `${(det.x_max - det.x_min) * scaleX}px`,
      height: `${(det.y_max - det.y_min) * scaleY}px`
    }
  }

  onMounted(() => {
    fetchImages()
  })
</script>

<template>
  <main class="min-h-screen bg-slate-100 p-8">
    <div class="max-w-3xl mx-auto space-y-8">
      
      <!-- Header -->
      <header class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <h1 class="text-2xl font-bold text-slate-800">Smiley Detection Dashboard</h1>
        <p class="text-sm text-slate-500 mt-1">Upload an image and view associated tasks.</p>
      </header>
      
      <!-- Uploaded Images List -->
      <section class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
        <h2 class="text-lg font-semibold text-slate-700">Uploaded Images</h2>

        <div v-if="images.length === 0" class="text-sm text-slate-400 italic">
          No images uploaded yet.
        </div>

        <div class="space-y-3">
          <div 
            v-for="img in images" 
            :key="img.guid"
            class="border border-slate-200 rounded-lg p-4 transition hover:border-blue-300 cursor-pointer"
            @click="toggleExpand(img)"
          >
            <!-- Summary Row -->
            <div class="flex justify-between items-center">
              <div>
                <p class="font-medium text-slate-800">{{ img.name }}</p>
                <p class="text-xs text-slate-400 font-mono mt-0.5">Path: {{ img.filepath }}</p>
              </div>
              <span class="text-xs font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">
                {{ expandedImages[img.guid] ? 'Collapse' : 'Expand' }}
              </span>
            </div>

            <!-- Expanded Details (Task IDs) -->
            <div v-if="expandedImages[img.guid]" class="mt-4 pt-4 border-t border-slate-100 space-y-3" @click.stop>
              <div class="flex gap-4 items-center">

                
                <!-- Image Preview with Bounding Box Overlay -->
                <div class="relative inline-block">
                  <img 
                    :src="`/${img.filepath}`" 
                    alt="Preview" 
                    class="w-48 h-auto rounded-lg border border-slate-200 block" 
                    @load="(e) => onImageLoad(e, img.guid)"
                  />
                  
                  <!-- Overlaid Bounding Boxes -->
                  <div 
                    v-for="det in activeDetections[img.guid]" 
                    :key="det.id"
                    class="absolute border-2 border-red-500 bg-red-500/20 pointer-events-none"
                    :style="calculateBoxStyle(det, img.guid)"
                  >
                    <span class="absolute -top-5 left-0 bg-red-500 text-white text-[10px] px-1 font-bold rounded whitespace-nowrap">
                      {{ (det.confidence * 100).toFixed(1) }}%
                    </span>
                  </div>
                </div>

                <div><button @click="startTaskOnImage(img.guid)">Start Task</button></div>
                <div>
                  <p class="text-xs text-slate-500"><span class="font-semibold">GUID:</span> {{ img.guid }}</p>
                  <p class="text-xs text-slate-500 mt-1"><span class="font-semibold">Group ID:</span> {{ img.upload_group_id }}</p>
                  <p class="text-xs text-slate-500 mt-1"><span class="font-semibold">Uploaded At:</span> {{ img.uploaded_at ? new Date(img.uploaded_at).toLocaleString() : '--' }}</p>
                </div>
              </div>

              <!-- Associated Task IDs List -->
              <div>
                <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Associated Task IDs (Click to View Boxes)</h4>
                <div v-if="!imageDetails[img.guid] || imageDetails[img.guid].length === 0" class="text-xs text-slate-400 italic">
                  No tasks associated with this image yet.
                </div>
                <ul v-else class="space-y-1">
                  <li 
                    v-for="taskId in imageDetails[img.guid]" 
                    :key="taskId" 
                    @click="fetchTaskDetections(img.guid, taskId)"
                    :class="[
                      'text-xs font-mono px-2 py-1 rounded cursor-pointer transition',
                      activeTaskId[img.guid] === taskId ? 'bg-blue-100 text-blue-800 font-bold' : 'text-slate-700 hover:bg-slate-100'
                    ]"
                  >
                    {{ taskId }}
                  </li>
                </ul>
              </div>
            </div>

          </div>
        </div>
      </section>

    </div>
  </main>
</template>

<style scoped>

  .image-container {
    position: relative;
    display: inline-block;
    max-width: 100%;
  }

  .target-image {
    display: block;
    width: 100%;
    height: auto;
  }

  .bounding-box {
    position: absolute;
    border: 2px solid #ef4444; /* Bright red border */
    background-color: rgba(239, 68, 68, 0.2); /* Semi-transparent red fill */
    pointer-events: none; /* Allows clicks to pass through if needed */
  }

  .box-label {
    position: absolute;
    top: -22px;
    left: 0;
    background-color: #ef4444;
    color: white;
    font-size: 12px;
    padding: 2px 6px;
    font-weight: bold;
    border-radius: 3px;
  }
</style>