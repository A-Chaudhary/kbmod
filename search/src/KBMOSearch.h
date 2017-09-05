/*
 * KBMOSearch.h
 *
 *  Created on: Jun 28, 2017
 *      Author: kbmod-usr
 */

#ifndef KBMODSEARCH_H_
#define KBMODSEARCH_H_

#include <parallel/algorithm>
#include <algorithm>
#include <functional>
#include <queue>
#include <iostream>
#include <fstream>
#include <chrono>
//#include <stdio.h>
#include <assert.h>
#include <float.h>
#include "common.h"
#include "PointSpreadFunc.h"
#include "ImageStack.h"

namespace kbmod {

extern "C" void
deviceSearch(int trajCount, int imageCount, int minObservations, int psiPhiSize,
			 int resultsCount, trajectory * trajectoriesToSearch, trajectory *bestTrajects,
		     float *imageTimes, float *interleavedPsiPhi, int width, int height);

class KBMOSearch {
public:
	KBMOSearch(ImageStack imstack, PointSpreadFunc PSF);
	void savePsiPhi(std::string path);
	void gpu(int aSteps, int vSteps, float minAngle, float maxAngle,
			float minVelocity, float maxVelocity, int minObservations);
	void cpu(int aSteps, int vSteps, float minAngle, float maxAngle,
			float minVelocity, float maxVelocity, int minObservations);
	void filterResults(int minObservations);
	std::vector<trajRegion> regionSearch(float xVel, float yVel,
			float radius, float minLH, int minObservations);
	trajRegion calculateLH(trajRegion& t);
	float findExtremeInRegion(float x, float y, int size,
			std::vector<RawImage>& pooledImgs, int poolType);
	// parameter for # of depths smaller to look than "size"
	// void minInRegion
	// void readPixel(int x, )
	int biggestFit(int x, int y, int maxX, int maxY); // inline?
	float readPixelDepth(int depth, int x, int y, std::vector<RawImage>& pooledImgs);
	std::vector<trajRegion> calculateLHBatch(std::vector<trajRegion>& tlist);
	std::vector<trajRegion> subdivide(trajRegion& t);
	std::vector<trajRegion> filterBounds(std::vector<trajRegion>& tlist,
			float xVel, float yVel, float ft, float radius);
	float squareSDF(float scale, float centerX, float centerY,
			float pointX, float pointY);
	std::vector<trajRegion> filterLH(std::vector<trajRegion>& tlist, float minLH, int minObs);
	float pixelExtreme(float pixel, float prev, int poolType);
	float maxMasked(float pixel, float previousMax);
	float minMasked(float pixel, float previousMin);
	std::vector<trajectory> getResults(int start, int end);
	std::vector<RawImage> getPsiImages();
    std::vector<RawImage> getPhiImages();
	void saveResults(std::string path, float fraction);
	void setDebug(bool d) { debugInfo = d; };
	virtual ~KBMOSearch() {};

private:
	void search(bool useGpu, int aSteps, int vSteps, float minAngle,
			float maxAngle, float minVelocity, float maxVelocity, int minObservations);
	std::vector<trajRegion> resSearch(float xVel, float yVel,
			float radius, int minObservations, float minLH);
	void clearPsiPhi();
	void clearPooled();
	void preparePsiPhi();
	void poolAllImages();
	std::vector<std::vector<RawImage>> poolSet(
			std::vector<RawImage>& imagesToPool,
			std::vector<std::vector<RawImage>>& destination, short mode);
	std::vector<RawImage> poolSingle(std::vector<RawImage>& mip, RawImage& img, short mode);
	void cpuConvolve();
	void gpuConvolve();
	void removeObjectFromImages(trajRegion& t);
	void saveImages(std::string path);
	void createSearchList(int angleSteps, int veloctiySteps, float minAngle,
			float maxAngle, float minVelocity, float maxVelocity);
	void createInterleavedPsiPhi();
	void cpuSearch(int minObservations);
	void gpuSearch(int minObservations);
	void sortResults();
	void startTimer(std::string message);
	void endTimer();
	long int totalPixelsRead;
	long int regionsMaxed;
	int maxResultCount;
	bool debugInfo;
	std::chrono::time_point<std::chrono::system_clock> tStart, tEnd;
	std::chrono::duration<double> tDelta;
	ImageStack stack;
	PointSpreadFunc psf;
	PointSpreadFunc psfSQ;
	std::vector<trajectory> searchList;
	std::vector<RawImage> psiImages;
	std::vector<RawImage> phiImages;
	std::vector<std::vector<RawImage>> pooledPsi;
	std::vector<std::vector<RawImage>> pooledPhi;
	std::vector<float> interleavedPsiPhi;
	std::vector<trajectory> results;

};

} /* namespace kbmod */

#endif /* KBMODSEARCH_H_ */
